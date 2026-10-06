# Current verification

Fresh metadata regression: **10/10 tops PASS**, ModelSim Intel FPGA Starter
Edition 2020.1 / simulator 2020.02. Compile: zero errors/warnings. See
[consolidated results](../../Development/Reports/voxel/RESULTS.md) and
[full regression evidence](../../Development/Reports/voxel/rtl_quick.json).
Source/vector SHA-256, commands, seeds, durations and accounting are recorded.

```sh
python3 FPGA/modelsim/run_regression.py --native-runtime "$HOME/intelFPGA/20.1" --no-waves
python3 Development/Tests/voxel/run_suite.py --mode stress --rtl
```

The four stale wildcard benches now connect and independently check metadata.
Packet tests use seven words, six-word prefetch, final timestamp backpressure,
and discard-through-TLAST after overlong packets. Both explicit accumulator
benches now drive and check metadata. Existing signed-coordinate, capacity,
collision, overflow, reset and stall assertions remain enabled. DMA readout and
end-to-end benches run eight-word RX with TKEEP/TLAST checks.

`tb_voxel_shared_vectors` adds the shipped 1,024-slot/2,048-entry configuration,
shared independent Python-generated expected vectors, long randomized stalls,
initialization traffic and an accounted reset-aborted result. Ten deterministic
seeds run 10,000 completed observations each. `--no-stalls` measures the same
streamed pipeline with ready high after its directed reset test. This is separate
from the narrower-count overflow tests, and does not alter shipped parameters.
No DUT internals are initialized or forced. Payload checks are validity gated.
The runner rejects errors/warnings/fatals, missing PASS or missing $finish even
when ModelSim exits zero, and has host and simulation watchdogs.

The two new DMA benches and shared-vector bench are included in the project
inventory. Fresh textual logs are retained. Historical September screenshots
and tracked WLF files are not current evidence; regenerate waves by omitting
`--no-waves`. These results replace the old four-word verification claims.
They are four-state RTL simulation, not synthesis, timing closure or board tests.
