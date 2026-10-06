"""Measured-pose join using an explicitly calibrated integer clock transform."""
from collections import deque
from dataclasses import dataclass

@dataclass(frozen=True)
class Alignment:
    boot_id: str
    source_anchor_ms: int
    common_anchor_us: int
    rate_num: int
    rate_den: int
    uncertainty_us: int

    def __post_init__(self):
        integers = (self.source_anchor_ms, self.common_anchor_us, self.rate_num,
                    self.rate_den, self.uncertainty_us)
        if not isinstance(self.boot_id, str) or not self.boot_id or any(type(v) is not int for v in integers):
            raise ValueError('clock calibration requires a boot ID and exact integer fields')
        if self.source_anchor_ms < 0 or not 0 <= self.common_anchor_us < 1 << 64:
            raise ValueError('clock anchor out of range')
        if self.rate_num <= 0 or self.rate_den <= 0 or self.uncertainty_us < 0:
            raise ValueError('invalid measured clock alignment')

    def convert(self, extended_ms):
        if self.rate_num <= 0 or self.rate_den <= 0 or self.uncertainty_us < 0:
            raise ValueError('invalid measured clock alignment')
        return self.common_anchor_us + ((extended_ms - self.source_anchor_ms) * 1000 * self.rate_num // self.rate_den)

class PoseAdapter:
    def __init__(self, drone_id, frame, alignment, max_age_us):
        if type(drone_id) is not int or not 0 <= drone_id <= 0xffffffff or not frame or type(max_age_us) is not int or max_age_us <= 0:
            raise ValueError('explicit drone, coordinate frame and positive age limit required')
        self.drone_id, self.frame, self.alignment, self.max_age_us = drone_id, frame, alignment, max_age_us
        self.poses = deque(maxlen=256)
        self.last_ms = None
        self.extended_ms = 0

    def pose(self, record):
        if record['drone_id'] != self.drone_id or record['frame'] != self.frame or record['units'] != 'mm':
            raise ValueError('pose frame/drone/units mismatch')
        if record['clock'] != 'aligned_common_us' or record['boot_id'] != self.alignment.boot_id:
            raise ValueError('pose clock/boot mismatch')
        xyz = record['position']
        time = record['timestamp_us']
        if len(xyz) != 3 or any(type(v) is not int or not -(1 << 31) <= v < 1 << 31 for v in xyz):
            raise ValueError('measured signed 3D millimetres required')
        if type(time) is not int or not 0 <= time < 1 << 64 or (self.poses and time <= self.poses[-1][0]):
            raise ValueError('nonmonotonic pose timestamp')
        self.poses.append((time, tuple(xyz)))

    def measurement(self, line, boot_id):
        if boot_id != self.alignment.boot_id:
            raise ValueError('reboot requires new measured alignment and adapter')
        fields = line.strip().split(',')
        if len(fields) != 6 or fields[0] != 'DATA':
            raise ValueError('expected ESP32 DATA record')
        # Manual centimetres and sample index are retained in the raw log only.
        _, x_cm, y_cm, index, stamp, rssi = fields
        int(x_cm); int(y_cm); int(index)
        stamp, rssi = int(stamp), int(rssi)
        if not 0 <= stamp <= 0xffffffff or not -(1 << 31) <= rssi < 1 << 31:
            raise ValueError('measurement range')
        if self.last_ms is None:
            # Anchor disambiguates which wrap epoch the first sample belongs to.
            delta = (stamp - (self.alignment.source_anchor_ms & 0xffffffff)) & 0xffffffff
            if delta >= 1 << 31:
                delta -= 1 << 32
            self.extended_ms = self.alignment.source_anchor_ms + delta
        else:
            delta = (stamp - self.last_ms) & 0xffffffff
            if delta == 0 or delta >= 1 << 31:
                raise ValueError('duplicate/out-of-order timestamp or reboot; cannot infer a new epoch')
            self.extended_ms += delta
        self.last_ms = stamp
        acquisition = self.alignment.convert(self.extended_ms)
        if not 0 <= acquisition < 1 << 64:
            raise ValueError('timestamp out of range')
        candidates = [pose for pose in self.poses if pose[0] <= acquisition]
        if not candidates:
            raise ValueError('missing measured pose at acquisition')
        pose_time, xyz = candidates[-1]
        if acquisition - pose_time + self.alignment.uncertainty_us > self.max_age_us:
            raise ValueError('stale pose or clock uncertainty exceeds age limit')
        return (*xyz, rssi, self.drone_id, acquisition)
