import contextlib
import io
import json
import os
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('MPLBACKEND', 'Agg')
from rf_mapping.voxel import wire
from rf_mapping.voxel.cli import live, replay
from rf_mapping.voxel.pose import Alignment, PoseAdapter
from rf_mapping.voxel.view import SparseMap

class FakeSerial:
    reject_observations = False
    def __init__(self, *args, **kwargs):
        self.parser = wire.Parser()
        self.output = bytearray()
        self.model = {}
        self.closed = False

    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def write(self, data):
        part = data[:3]
        for message in self.parser.feed(part):
            code = int(self.reject_observations and message.kind == wire.OBSERVATION)
            self.output.extend(wire.Message(wire.ACK,message.session,message.sequence,struct.pack('<II',code,32)).encode())
            if code:
                continue
            if message.kind == wire.OBSERVATION:
                x,y,z,rssi,drone,stamp=wire.OBS.unpack(message.payload)
                key=(x//500,y//500,z//500)
                new = key not in self.model
                if new: self.model[key]=[len(self.model),0,0]
                state=self.model[key];state[1]+=rssi;state[2]+=1
                payload=wire.UPDATE.pack(state[0],*key,state[1],state[2],int(new),drone,stamp)
                self.output.extend(wire.Message(wire.RESULT,message.session,message.sequence,payload).encode())
            elif message.kind == wire.STATUS:
                for kind in (wire.DIAGNOSTIC, wire.LATENCY):
                    self.output.extend(wire.Message(kind,message.session,message.sequence,bytes(128)).encode())
            elif message.kind == wire.SNAPSHOT:
                for key,state in self.model.items():
                    payload=wire.SLOT.pack(state[0],*key,state[1],state[2])
                    self.output.extend(wire.Message(wire.SNAPSHOT_SLOT,message.session,message.sequence,payload).encode())
                self.output.extend(wire.Message(wire.SNAPSHOT_END,message.session,message.sequence,struct.pack('<I',len(self.model))).encode())
        return len(part)
    def read(self, size):
        value=bytes(self.output[:7]);del self.output[:7];return value

class HostTests(unittest.TestCase):
    def test_wire_fragmentation_corruption_bounds(self):
        rng=random.Random(1729)
        for size in range(129):
            payload=bytes(rng.randrange(256) for _ in range(size))
            m=wire.Message(wire.OBSERVATION,(1<<64)-1,0xffffffff,payload)
            encoded=m.encode();parser=wire.Parser();decoded=[]
            for byte in encoded: decoded.extend(parser.feed(bytes([byte])))
            self.assertEqual(decoded,[m])
            corrupt=bytearray(encoded);corrupt[len(corrupt)//2]^=1
            list(parser.feed(corrupt));self.assertGreater(parser.errors,0)
        parser=wire.Parser()
        list(parser.feed(b'a'*100000+b'~'))
        self.assertEqual(len(parser.raw),0);self.assertEqual(parser.errors,1)
        list(parser.feed(b'~}a~'));self.assertEqual(parser.errors,2)

    def adapter(self, anchor=(1<<32)-2, common=(1<<53)+17):
        return PoseAdapter(202,'lab_enu',Alignment('boot-A',anchor,common,1,1,20),1500)
    def pose(self, adapter, time, xyz=(-1,500,1000)):
        adapter.pose(dict(drone_id=202,frame='lab_enu',units='mm',clock='aligned_common_us',boot_id='boot-A',position=xyz,timestamp_us=time))
    def test_alignment_rejects_float_timestamps(self):
        with self.assertRaises(ValueError): Alignment('boot', 0, float(1 << 54), 1, 1, 0)
        with self.assertRaises(ValueError): Alignment('boot', 0, 1, 1, 0, 0)
        with self.assertRaises(ValueError): Alignment('', 0, 1, 1, 1, 0)

    def test_pose_precision_wrap_reboot_and_expiry(self):
        a=self.adapter();base=a.alignment.common_anchor_us
        self.pose(a,base)
        self.assertEqual(a.measurement('DATA,12,30,0,4294967294,-63','boot-A'),(-1,500,1000,-63,202,base))
        self.pose(a,base+1000)
        self.assertEqual(a.measurement('DATA,12,30,1,4294967295,-67','boot-A')[-1],base+1000)
        self.pose(a,base+2000)
        self.assertEqual(a.measurement('DATA,12,30,2,0,-65','boot-A')[-1],base+2000)
        with self.assertRaises(ValueError): a.measurement('DATA,0,0,3,0,-60','boot-A')
        with self.assertRaises(ValueError): a.measurement('DATA,0,0,3,1,-60','boot-B')
        with self.assertRaises(ValueError): a.measurement('DATA,0,0,4,3,-60','boot-A')
        b=self.adapter()
        with self.assertRaises(ValueError): b.measurement('DATA,0,0,0,4294967294,-63','boot-A')
        with self.assertRaises(ValueError): self.pose(b,base,(0,0))
    def test_sparse_extremes_fractional_export_and_render(self):
        sparse=SparseMap()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data.wire';image=Path(directory)/'map.png'
            with path.open('wb') as out:
                for index,key in enumerate(((-4294968,0,0),(4294967,0,0))):
                    m=wire.Message(wire.RESULT,1,index+1,wire.UPDATE.pack(index,*key,-131,2,1,202,(1<<64)-1))
                    record=wire.update_record(m);sparse.apply(record);out.write(m.encode())
                    self.assertEqual(record['mean_dbm'],-65.5)
            result=replay(path,image)
            self.assertEqual(result,dict(occupied=2,framing_errors=0))
            self.assertGreater(image.stat().st_size,10000)
        self.assertEqual(len(sparse.slots),2)
    def test_live_partial_serial_and_replay(self):
        observations=[(-1,-500,-501,-63,101,0),(-1,-500,-501,-68,202,(1<<64)-1)]
        with tempfile.TemporaryDirectory() as directory, patch('serial.Serial',FakeSerial), contextlib.redirect_stderr(io.StringIO()):
            log=Path(directory)/'capture.wire'
            counters=live('mock',observations,log,True)
            self.assertEqual(counters['completed'],2)
            parser=wire.Parser();records=[wire.update_record(m) for m in parser.feed(log.read_bytes()) if m.kind==wire.RESULT]
            self.assertEqual(records[-1]['mean_dbm'],-65.5)
            self.assertEqual(records[-1]['count'],2)
    def test_live_admission_drop_accounting(self):
        class Rejected(FakeSerial):
            reject_observations = True
        with tempfile.TemporaryDirectory() as directory, patch('serial.Serial',Rejected), contextlib.redirect_stderr(io.StringIO()):
            counts = live('mock', [(0,0,0,-60,1,1)], Path(directory)/'wire', True)
            self.assertEqual((counts['input'],counts['sent'],counts['completed'],counts['firmware_dropped'],counts['source_dropped']), (1,1,0,1,0))

    def test_live_lost_response_stops_without_retry(self):
        class LostResponse(FakeSerial):
            def write(self, data):
                for message in self.parser.feed(data):
                    if message.kind == wire.START:
                        self.output.extend(wire.Message(wire.ACK,message.session,0,struct.pack('<II',0,32)).encode())
                return len(data)
        with tempfile.TemporaryDirectory() as directory, patch('serial.Serial',LostResponse), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(TimeoutError):
                live('mock',[(0,0,0,-60,1,1)],Path(directory)/'wire',True,timeout=0.01)

    def test_live_missing_start_stops_without_retry(self):
        class Disconnected(FakeSerial):
            def write(self,data): return len(data)
        with tempfile.TemporaryDirectory() as directory, patch('serial.Serial',Disconnected), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(TimeoutError): live('mock',[],Path(directory)/'wire',True,timeout=0.01)
        with self.assertRaises(ValueError): live('mock',[],Path('/unused'),False)


class LinkerMapTests(unittest.TestCase):
    def test_ddr_placement_guard(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('map_check',Path(__file__).with_name('check_linker_map.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        valid='.voxel_ddr 0x00101000 0x00010000\n0x00101000 __voxel_ddr_start\n0x00111000 __voxel_ddr_end\n'
        self.assertEqual(module.check(valid,0x100000,0x40000000)['bytes'],65536)
        for bad in (valid.replace('00101000','00001000'),valid.replace('00010000','40000000'),valid.replace('.voxel_ddr','.bss'),valid.replace('__voxel_ddr_end','bad')):
            with self.assertRaises(ValueError):module.check(bad,0x100000,0x40000000)

if __name__=='__main__': unittest.main()
