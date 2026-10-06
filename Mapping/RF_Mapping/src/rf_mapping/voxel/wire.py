"""Version 1 bounded escaped frames; exact integer payloads and CRC-32/ISO-HDLC."""
from dataclasses import dataclass
import struct
import zlib

VERSION, LIMIT = 1, 128
BOUNDARY, ESCAPE = 126, 125
START, OBSERVATION, STATUS, SNAPSHOT = 1, 2, 3, 4
RESULT, DIAGNOSTIC, ACK, SNAPSHOT_SLOT, SNAPSHOT_END = range(128, 133)
LATENCY = 133
HEADER = struct.Struct('<BBHQI')
OBS = struct.Struct('<iiiiIQ')
SLOT = struct.Struct('<IqqqqI')
UPDATE = struct.Struct('<IqqqqIIIQ')

@dataclass(frozen=True)
class Message:
    kind: int
    session: int
    sequence: int
    payload: bytes = b''

    def encode(self):
        if len(self.payload) > LIMIT:
            raise ValueError('payload exceeds frame bound')
        raw = HEADER.pack(VERSION, self.kind, len(self.payload), self.session, self.sequence) + self.payload
        raw += struct.pack('<I', zlib.crc32(raw))
        out = bytearray([BOUNDARY])
        for byte in raw:
            if byte in (BOUNDARY, ESCAPE):
                out.extend((ESCAPE, byte ^ 32))
            else:
                out.append(byte)
        out.append(BOUNDARY)
        return bytes(out)

class Parser:
    def __init__(self):
        self.raw = bytearray()
        self.escaped = self.discard = False
        self.errors = 0

    def feed(self, data):
        for byte in data:
            if byte == BOUNDARY:
                message = None
                if self.raw or self.discard or self.escaped:
                    try:
                        if self.discard or self.escaped or len(self.raw) < HEADER.size + 4:
                            raise ValueError('incomplete frame')
                        version, kind, length, session, seq = HEADER.unpack_from(self.raw)
                        if version != VERSION or length > LIMIT or len(self.raw) != HEADER.size + length + 4:
                            raise ValueError('invalid header')
                        if zlib.crc32(self.raw[:-4]) != struct.unpack_from('<I', self.raw, len(self.raw)-4)[0]:
                            raise ValueError('CRC mismatch')
                        message = Message(kind, session, seq, bytes(self.raw[HEADER.size:-4]))
                    except (ValueError, struct.error):
                        self.errors += 1
                self.raw.clear()
                self.escaped = self.discard = False
                if message is not None:
                    yield message
            elif not self.discard:
                if self.escaped:
                    if byte not in (BOUNDARY ^ 32, ESCAPE ^ 32):
                        self.discard = True
                        continue
                    byte ^= 32
                    self.escaped = False
                elif byte == ESCAPE:
                    self.escaped = True
                    continue
                if len(self.raw) == HEADER.size + LIMIT + 4:
                    self.discard = True
                else:
                    self.raw.append(byte)

def update_record(message):
    if message.kind not in (RESULT, SNAPSHOT_SLOT):
        raise ValueError('not voxel data')
    expected_size = UPDATE.size if message.kind == RESULT else SLOT.size
    if len(message.payload) != expected_size:
        raise ValueError('invalid voxel payload length')
    slot, x, y, z, total, count = SLOT.unpack_from(message.payload)
    flags, drone, timestamp = (0, None, None)
    if message.kind == RESULT:
        flags, drone, timestamp = struct.unpack_from('<IIQ', message.payload, SLOT.size)
    if slot >= 1024 or flags not in (0, 1, 2, 6) or (not flags & 2 and not count):
        raise ValueError('invalid slot/flags/count')
    return dict(snapshot=message.kind == SNAPSHOT_SLOT, session=message.session, sequence=message.sequence, slot=slot,
                voxel=[x, y, z], lower_m=[v / 2 for v in (x, y, z)],
                size_m=0.5, sum_dbm=total, count=count,
                mean_dbm=total / count if count else None, flags=flags,
                drone_id=drone, timestamp_us=timestamp)
