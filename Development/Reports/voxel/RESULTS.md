# Fresh software and RTL verification

All required minimum stress counts completed. Production RTL, wrappers, XSA and
bitstreams match baseline `4dfa3979b28f42e21d32ce269452b24917a0f2b4` byte for byte.
Implementation commits: `c365ef6` (verification repairs), `4f9ecd8` (continuous
software and shared-vector path), `1a5a7eb` (ESP burst control and live RSS checks).
The working tree was clean at task start and HEAD matched the reviewed baseline.

| Evidence | Work completed | Result |
|---|---|---|
| Full four-state regression | 22 compiled files; 10 independent tops; seed 20260929 | 10/10 PASS, zero compile/simulation errors or warnings |
| Full-size RTL stress | seeds 1–10 × 10,000; 1,024 slots / 2,048 buckets | 100,010 submitted = 100,000 completed + 10 intentional reset aborts; 64,100 accepted, 35,900 capacity rejections |
| Host integration stress | seeds 1–10 × 100,000, ASan + nonrecovering UBSan | 1,000,000 submitted/started/completed; 604,100 accepted, 395,900 rejected, 0 dropped |
| Host soak | seed 42 × 1,000,000 | 1,000,000 submitted/started/completed; 600,410 accepted, 399,590 rejected, 0 dropped |
| Host quick | seed 1 × 10,000 | 6,410 accepted, 3,590 rejected; no loss/duplication |
| BSP adapter | actual zybo_main.c with mocked register/driver/cache calls, legacy + SDT | both PASS; **not a vendor build** |
| Host unit/integration edges | 11 Python tests plus C fault suite | PASS, including fragmented live serial, ESP burst commands, pose expiry/reboot/wrap, replay/rendering and linker-map guard |
| Existing package | 72 unittest tests; isolated pytest also 72 | PASS; compileall and wheel build PASS |

Counts include capacity rejections intentionally; the first 1,024 unique voxels
fill each hardware epoch. Golden vectors use signed RSSI extremes for verification,
not physically realistic RSSI data. Every completed observation is classified;
no traffic was reduced and no assertion was disabled to obtain a pass. C counters
also distinguish admission drops, error-stopped queued work and ambiguous in-flight
work. Reset tests account for discarded transactions explicitly.

Fault and edge coverage includes metadata through every stage; signed coordinate
floor boundaries/extremes; repeated voxels and interleaved drones; timestamp low
word rollover and u32/u64 extremes; constructed hash collisions; full capacity
then successful existing-key updates; count saturation with narrowed testbench
counters; short/long/missing-TLAST packets; initialization; reset during partial,
pending and held work; long randomized stalls; invalid flags/slots/counts/metadata;
stale/duplicate results; RX/TX start/error/timeout/length failures; cache ordering;
queue saturation; corrupt/fragmented serial; slow/disconnected consumers; session
recovery by coordinated restart; missing/stale/future poses and boot changes.
No hardware defect surfaced in these exercised cases. This is not an exhaustive
proof of RTL or board behavior.

## Measured host and simulated performance

Host: 11th Gen Intel(R) Core(TM) i7-1185G7 @ 3.00GHz; GCC 13.3.0, Python as recorded in
JSON, NumPy 2.4.6, Matplotlib 3.11.0, pySerial 3.5. ModelSim Intel FPGA Starter
Edition 2020.1 / simulator 2020.02 ran fresh compile/elaboration/simulation without license errors.
The installed PRoot vlog launcher is bypassed using its private native ELF loader.
No Vivado/Vitis/XSCT/ARM compiler or accessible serial board was found.

The 10 C stress runs took **31.063 s** total
(**32,192 observations/s**) including vector file I/O, serial
framing, cooperative delayed-DMA mocks, validation, mirror and export. Python
independent output/snapshot/replay parsing took **38.690 s** total.
The million-observation C soak took **27.565 s**
(**36,278 observations/s**), and its Python checker
**40.717 s**. These are instrumented host measurements;
some runs overlapped other verification work and are not isolated CPU benchmarks.
Mock microsecond ticks are synthetic and are never reported as board latency.

The fixed C fixture is **50,240 bytes**, with no application heap allocation.
Largest measured C process RSS was **14,080 KiB** (bound: 65,536 KiB).
Python stores at most 1,024 slots and bounded parser buffers. Live RSS sampled
throughout checking peaked at **83,852 KiB**, with at most **68 KiB**
growth after the 10,000-observation warmup (bound: 16,384 KiB). Import-time
high-water RSS was deliberately replaced by live resident sampling, so it cannot
mask later growth. Raw vectors/captures grow on disk intentionally; generation,
hashing and checking stream them.

RTL stress invocations took **57.830 s** host wall time in total.
The no-stall streamed full-pipeline run completed 10,000 observations over
**82,046 measured clocks** (8.2046 clocks/result),
with final-TX-beat to final-RX-beat latency min/mean/max
**52 / 53.0005 / 2053 clocks**.
This includes initialization/backlog effects; it is not a single-in-flight board
DMA benchmark. Individual seed latency/stall counts are retained in RTL JSON.
Readout unit tests additionally verify one eight-word packet every eight clocks.
100 MHz is a configuration value, not a measured clock or timing-closure result.

## Evidence, commands and limitations

- [Host quick](quick.json), [host stress](stress.json), [host soak](soak.json):
  exact commands, final source hashes, seeds, counts, GCC/Python versions,
  per-stage durations, memory samples and compiler/test transcripts.
- [Full RTL regression](rtl_quick.json), [10-seed RTL stress](rtl_stress.json),
  [RTL throughput](rtl_throughput.json): source/vector hashes, simulator version,
  actual PASS accounting, commands and durations. RTL evidence predates only the
  isolated ESP bridge refinements; all RTL/bench/runner hashes still match.
- [Hardware manifest](hardware_contract.json) and
  [HWH clock/reset/interrupt connections](hardware_connections.json): parameters
  and frozen hardware hashes. PL blocks use peripheral_aresetn; DMA reset outputs
  and DMA interrupt outputs are unconnected. init_done/map_full are not software
  status registers. HWH does not prove bitstream behavioral identity by itself.
- [Compatibility/tool evidence](compatibility.json),
  [test commands and coverage](../../Tests/voxel/README.md),
  [architecture/operation](../../../FPGA/software/voxel/README.md),
  [sources and choices](../../../FPGA/software/voxel/SOURCES.md).

One environment issue remains recorded: plain `python3 -m pytest -q` auto-loaded
an unrelated ROS plugin and failed before tests because `lark` is absent. With
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, the repository's 72 tests passed, with two
expected existing metadata warnings. No repository test was disabled. Native
unittest discovery independently passed the same 72 tests.

**Pending physical/vendor validation:** compile/link the application in Vitis
2024.2; check the real linker map and generated BSP macros; execute the documented
board smoke/stress and latency/UART/drop procedure; verify measured 3D pose
hardware, coordinate-frame calibration, clock alignment and reboot detection.
No board throughput, utilization or timing-closure results are claimed. No
implementation reports were available. All requested host/RTL stress goals were
met; these unavailable Vitis/board checks are the remaining validation limits.
