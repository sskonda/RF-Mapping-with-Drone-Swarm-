# ModelSim waveform screenshots

Actual ModelSim Wave-window captures from the passing September 29, 2026 regression.
Each filename identifies the RTL module and behavior. See
[verification results](../modelsim/VERIFICATION.md) and
[reproduction instructions](../modelsim/README.md).

| Screenshot | What to inspect |
| --- | --- |
| [01 — AXI increment, wraparound, and backpressure](01_axis_passthrough_increment_wraparound_backpressure.png) | Input 41 becomes output 42 after a clock edge. Output 42 stays stable while the sink is blocked. Input 4294967295 wraps to output 0; TLAST follows its word. |
| [02 — Packet fields, prefetch, and backpressure](02_rf_packet_unpacker_signed_fields_prefetch_backpressure.png) | The first tuple `(-1000, 2000, -500, -65)` remains stable. The next X/Y/Z (`101, 202, 303`) forward while the observation is held; RSSI `-77` waits for observation readiness. |
| [03 — Signed voxel floor and four-stage stall](03_voxel_signed_floor_four_stage_pipeline_stall.png) | With a 500 mm grid, `(-1, -500, -501)` becomes `(-1, -1, -2)`. `stage_valid` fills all four stages. Output coordinates and RSSI stay stable until `voxel_ready`. |
| [04 — Lookup allocation, hit, and full-map rejection](04_voxel_lookup_allocate_hit_full_rejection.png) | A repeated key retains slot 0 with `lookup_new=0`. New keys allocate slots until `used_voxels=5`; further unseen keys assert `lookup_rejected`. |
| [05 — Signed RSSI sum and count](05_voxel_accumulator_signed_sum_count.png) | The first result is sum `-63`, count 1. Another `-67` in the same slot produces sum `-130`, count 2. Signed limits and rejection cases follow. |
| [06 — Lookup collisions and linear probing](06_voxel_lookup_collisions_linear_probing.png) | Deliberately colliding keys cause `address` to wrap from bucket 7 to 0 and `attempts` to increase. Repeated keys recover their original slots. |
| [07 — Count saturation and overflow](07_voxel_accumulator_count_saturation_overflow.png) | A 3-bit count saturates at 7. Further updates assert `acc_overflow` and `acc_rejected`, retaining the previous count and sum. A new-slot request reinitializes statistics. |
| [08 — Accumulator backpressure without duplicate updates](08_voxel_accumulator_backpressure_no_duplicate_update.png) | With `acc_ready=0`, the result's valid bit, count, and sum remain stable and input readiness stays low. On release, the next accepted observation updates the statistics once. |

All time axes are in ns. Coordinates, RSSI, and sums are signed decimal; AXI
increment data and counters are unsigned. Green traces are requests, blue traces
are results, and orange traces show selected internal state. The value column
samples the yellow cursor. Invalid payloads may be unknown or retain old data;
interpret them only while valid is asserted. Complete traces are saved in
[`../modelsim/waves`](../modelsim/waves/).
