# FPGA RTL verification — September 29, 2026

**PASS: 7/7 testbench tops**, covering every `.sv` in `FPGA/rtl` and all five
wrappers. Compilation and final simulation logs report **zero errors and zero
warnings**. No RTL or wrapper source was changed.

Simulator: ModelSim Intel FPGA Starter Edition 2020.1, simulator build 2020.02.
SystemVerilog random seed: `20260929`. Simulation resolution: `1 ps`.
The machine's timestamps in [results.json](logs/results.json) are UTC; the local
run date is September 29 in America/New_York.

| RTL / integration | Testbench | Checked behavior | Result |
| --- | --- | --- | --- |
| `axis_passthrough.sv` | `axis_passthrough_tb` (new) | 8/32/64-bit increment and wraparound; registered output; TLAST; continuous transfers; source gaps; stable stalled output; reset drops exactly one result | 81 outputs per width; 36 stalled cycles and 37 simultaneous transfers per width |
| `rf_packet_unpacker.sv` | `rf_packet_unpacker_tb` | Unchanged AXI forwarding; signed X/Y/Z/RSSI; observation retention; X/Y/Z prefetch with blocked RSSI; independent AXI stalls; early/missing TLAST; reset of partial and complete packets | 56 forwarded words; 11 consumed observations |
| `voxel.sv` | `voxel_tb` | Signed floor boundaries; shifted origins; extreme signed positions and origins; size 1 and 500; four-stage fill/backpressure; throughput; RSSI ordering; reset recovery | Default and shifted grids: 37 outputs each; full signed range: 35 |
| Unpacker → voxel | `rf_voxel_pipeline_tb` | Four voxel stages plus unpacker observation register and three pending words; AXI forwarding; signed boundaries; independently stalled sinks; no loss/duplication | 32 forwarded words; 8 voxels |
| `voxel_lookup.sv` | `tb_voxel_lookup` | 1/5/8/1024 slots; 2/8/8/2048 buckets; signed 33-bit keys; initialization duration; independent full-key model; constructed collisions and wraparound; full-table rejection; hits when full; stalls; interrupted lookup/reset | 6,209 results across four configurations; reset-aborted requests accounted for |
| `voxel_accumulator.sv` | `tb_voxel_accumulator` | 1/5/1024 slots; 3/32-bit counts; independent sum/count model; signed limits; repeated slots; invalid slot/upstream rejection; saturation/overflow; stalled output; reset before writeback and while holding a result; two-cycle input spacing | 5,642 results across three configurations; two reset-aborted requests per configuration |
| Voxel → lookup → accumulator | `tb_voxel_accumulator_pipeline` | Independent coordinate-to-statistics model; repeated voxels; signed extremes; map full; sink and upstream stalls; coordinated reset and RAM slot reuse | 2,008 results; 396 rejections; 2,907 upstream stall cycles |

## Testbench repairs

The original baseline passed the lookup, accumulator, and accumulator pipeline
benches. Three older benches did not match the current RTL:

- `voxel_tb` and `rf_voxel_pipeline_tb` connected `.*` to signals named `vx/vy/vz`,
  while the wrapper now exports `voxel_x/voxel_y/voxel_z`. Explicit connections
  restore elaboration.
- `rf_packet_unpacker_tb` and `voxel_tb` required reset to clear invalid payload
  registers. The current RTL resets valid/control bits. Tests now check that
  contract and still verify every valid result and post-reset recovery.
- The unpacker can prefetch X/Y/Z while holding an observation. Tests now track
  the packet field independently and require the fourth word to backpressure.
- The voxelizer now contains four elastic stages. The unit test fills all four
  before checking input backpressure and waits for the whole pipeline to drain.
  The integration test checks all five observation slots plus the three pending
  AXI words (23 accepted words while the sink is blocked), then drains five voxels.
  Its directed stall is long enough to cover prefetch and at least six blocked
  fourth-word cycles.

The new AXI bench follows the existing `voxel_tb.sv` conventions: `1ns/1ps`, a
10 ns clock, parameterized cases, wrapper DUT, falling-edge stimulus tasks,
rising-edge scoreboard before NBA updates, stable-payload checks, PASS messages,
and a watchdog using `$fatal`.

## Evidence and scope

[Waveform screenshots](../waveform_screenshots/README.md) are actual captures of
ModelSim's Wave window from the passing WLF recordings. They illustrate selected
directed cases; the self-checking regressions cover the full stimulus sequences.
This is RTL simulation verification, not synthesis, timing closure, or board testing.
