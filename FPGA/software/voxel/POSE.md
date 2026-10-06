# Measured-pose bridge

The unchanged ESP32 sketch emits
`DATA,x_cm,y_cm,sample_index,millis32,rssi_dbm`. Its x/y centimetres come from a
manual MEASURE command; it has no measured z, pose sensor, hardware time sync,
unique boot ID or drone ID. The bridge never uses these x/y values as measured
coordinates. Raw DATA, including manual coordinates, is preserved in the log.

Use one `PoseAdapter` per explicitly assigned u32 drone ID and source connection.
A measured-pose producer must provide JSON lines with these required fields:

```json
{"type":"pose","drone_id":202,"frame":"lab_enu","units":"mm","clock":"aligned_common_us","boot_id":"calibration-boot-id","position":[-1,500,1000],"timestamp_us":123456789}
```

The example specifies a schema, not a measured position. Supply all three
signed 32-bit millimetre coordinates from motion capture, surveyed localization,
GNSS/RTK plus height, or another validated pose source. The named frame must have
a documented physical origin and axis convention shared by all drones (for
example surveyed ENU). Transform sensor/body frames into that frame externally
and document calibration and uncertainty. Pose timestamps are acquisition times,
not PC serial receive times. Pose JSON is bounded to 1,024 characters on serial.

The configuration contains `drone_id`, `frame`, `max_pose_age_us`, and alignment:
`boot_id`, `source_anchor_ms` (unwrapped integer ESP clock), `common_anchor_us`,
positive `rate_num/rate_den`, and nonnegative `uncertainty_us`.
Time conversion uses integer arithmetic:

`common_anchor_us + (extended_ms-source_anchor_ms)*1000*rate_num//rate_den`.

Obtain the anchor/rate/uncertainty from an actual shared trigger, timestamp
exchange with a quantified bound, or logged calibration experiment. Merely
setting both clocks to zero is not synchronization. Preserve microseconds as
integers throughout; do not pass through floating-point seconds. The replay
fixture intentionally exercises times above 2^53.

The adapter accepts only strictly increasing poses and selects the newest pose
at or before acquisition. It rejects absent poses, future-only poses, or
`acquisition-pose_time+alignment_uncertainty > max_pose_age_us`. No interpolation
or invented z is applied. Keep poses arriving ahead of their matching RF records;
otherwise the bounded bridge rejects the measurement. Account separately for RF
sample timing accuracy: WiFi.RSSI is sampled by the ESP sketch near `millis()`;
that is not a radio hardware timestamp.

Modulo-2^32 millisecond differences below half the range permit wrap extension.
Zero/backward/ambiguous differences reject; reconnect/reboot requires a fresh
boot ID and measured alignment, a new adapter, and a new acquisition session.
The unchanged ESP32 cannot distinguish every reboot from wrap. Its firmware
startup status is treated as a hard stop by the live bridge; missed startup on
reconnect must be handled by the operator/pose producer. Do not reuse alignment
across serial reconnects or infer a boot epoch from a small timestamp alone.
Opening the ESP serial port may assert DTR and reboot it; calibrate and manage
that reset before a live run. The bridge sends no MEASURE commands automatically.

Deterministic replay consumes ordered event JSONL (pose events plus
`{"type":"rssi","boot_id":"...","line":"DATA,..."}`). The included fixture is
explicitly synthetic and expected output is checked into the repository.

Live example, after calibration and coordinated Zybo restart:

```sh
rf-voxel bridge-live --config measured-alignment.json \
  --esp-port /dev/ttyUSB0 --pose-port /dev/ttyACM0 --zybo-port /dev/ttyUSB1 \
  --raw-log raw-events.jsonl --wire-log voxel-results.wire --fresh-map
```

Physical integration still needs measured 3D pose hardware and its schema
producer, surveyed frame transforms, clock calibration and boot detection, an
explicit per-drone identity assignment, ESP measurement triggering, and verified
Zybo UART wiring/port selection. None is fabricated by deterministic replay.
