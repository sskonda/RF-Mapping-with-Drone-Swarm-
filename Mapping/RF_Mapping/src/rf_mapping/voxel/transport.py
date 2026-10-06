"""Bounded acquisition transport; plotting runs in another process."""
import json
from pathlib import Path
import queue
import secrets
import struct
import sys
import threading
import time
from . import wire

def live(port, observations, log_path, fresh_map, timeout=3.0, source_rate=0.0):
    import serial
    if not fresh_map:
        raise ValueError('--fresh-map attestation requires coordinated FPGA/software restart first')
    arrivals = queue.Queue(maxsize=256)
    stopped = threading.Event()
    counts = {'input': 0, 'source_dropped': 0, 'firmware_dropped': 0, 'sent': 0, 'accepted': 0, 'rejected': 0, 'completed': 0}
    producer_errors = []

    def produce():
        try:
            for observation in observations:
                if stopped.is_set():
                    break
                if source_rate > 0:
                    if stopped.wait(1.0 / source_rate):
                        break
                counts['input'] += 1
                try:
                    # Validate the complete payload before entering the transport queue.
                    payload = wire.OBS.pack(*observation)
                    arrivals.put_nowait(payload)
                except queue.Full:
                    counts['source_dropped'] += 1
        except Exception as error:
            producer_errors.append(error)
        finally:
            stopped.set()

    session = secrets.randbits(64) or 1
    parser = wire.Parser()
    pending = {}
    sequence = 1
    tx = bytearray(wire.Message(wire.START, session, 0, struct.pack('<I', 0x46524553)).encode())
    ready = False
    finishing = 0
    control_sequence = None
    control_started = 0.0
    snapshot_count = 0
    started = time.monotonic()
    thread = threading.Thread(target=produce, daemon=True)
    try:
        with serial.Serial(port, 115200, timeout=0, write_timeout=0) as device, Path(log_path).open('wb') as raw:
            thread.start()
            while True:
                now = time.monotonic()
                if producer_errors:
                    raise RuntimeError('measurement producer failed') from producer_errors[0]
                if not ready and now - started > timeout:
                    raise TimeoutError('START response missing; verify coordinated restart, never resend observations')
                if finishing in (1, 2) and now - control_started > timeout:
                    raise TimeoutError('final diagnostics/snapshot incomplete; capture retained')
                if pending and now - min(pending.values()) > timeout:
                    raise TimeoutError('result missing; stop session, preserve logs, coordinated restart required')
                data = device.read(4096)
                if data:
                    raw.write(data)
                    raw.flush()
                for message in parser.feed(data):
                    if message.session != session:
                        raise ValueError('stale/wrong UART session')
                    if message.kind == wire.ACK:
                        code, _credits = struct.unpack('<II', message.payload)
                        if message.sequence == 0:
                            if code:
                                raise ValueError('START rejected')
                            ready = True
                        elif code:
                            if message.sequence == control_sequence:
                                raise ValueError('final control request rejected')
                            if message.sequence not in pending:
                                raise ValueError('unknown drop ACK')
                            del pending[message.sequence]
                            counts['firmware_dropped'] += 1
                    elif message.kind == wire.RESULT:
                        if message.sequence not in pending:
                            raise ValueError('duplicate/stale result')
                        record = wire.update_record(message)
                        del pending[message.sequence]
                        counts['completed'] += 1
                        counts['rejected' if record['flags'] & 2 else 'accepted'] += 1
                    elif message.kind == wire.DIAGNOSTIC:
                        print(json.dumps({'firmware_status': struct.unpack('<16Q', message.payload)}), file=sys.stderr)
                    elif message.kind == wire.LATENCY:
                        print(json.dumps({'latency_bins_us_log2': struct.unpack('<16Q', message.payload)}), file=sys.stderr)
                        if finishing == 1 and message.sequence == control_sequence:
                            control_sequence = sequence
                            sequence += 1
                            tx.extend(wire.Message(wire.SNAPSHOT, session, control_sequence).encode())
                            finishing = 2
                            control_started = now
                    elif message.kind == wire.SNAPSHOT_SLOT:
                        if finishing != 2 or message.sequence != control_sequence:
                            raise ValueError('unsolicited snapshot')
                        record = wire.update_record(message)
                        if record['slot'] != snapshot_count:
                            raise ValueError('missing/duplicate snapshot slot')
                        snapshot_count += 1
                        control_started = now
                    elif message.kind == wire.SNAPSHOT_END:
                        if finishing != 2 or message.sequence != control_sequence or struct.unpack('<I', message.payload)[0] != snapshot_count:
                            raise ValueError('invalid snapshot completion')
                        finishing = 3
                if parser.errors:
                    raise ValueError('corrupt UART stream; do not retry ambiguous observations')
                if ready and not finishing and not tx and len(pending) < 8:
                    try:
                        payload = arrivals.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        if sequence > 0xffffffff:
                            raise RuntimeError('sequence exhausted; coordinated restart required')
                        tx.extend(wire.Message(wire.OBSERVATION, session, sequence, payload).encode())
                        pending[sequence] = now
                        counts['sent'] += 1
                        sequence += 1
                if tx:
                    written = device.write(tx)
                    del tx[:written]
                if ready and stopped.is_set() and arrivals.empty() and not pending and not tx:
                    if finishing == 0:
                        if sequence > 0xfffffffe:
                            raise RuntimeError('sequence budget exhausted before final controls')
                        control_sequence = sequence
                        sequence += 1
                        tx.extend(wire.Message(wire.STATUS, session, control_sequence).encode())
                        finishing = 1
                        control_started = now
                    elif finishing == 3:
                        break
                time.sleep(0.0005)
    finally:
        stopped.set()
        print(json.dumps({'session': session, **counts}), file=sys.stderr)
    return counts
