# Current verification

Fresh metadata regression: **9/9 tops PASS**, ModelSim Intel FPGA Starter Edition
2020.1 / simulator 2020.02, seed 20260929. See `logs/results.json` for run time,
source SHA-256 hashes and individual results. Compile: zero errors/warnings.

Command from repository root:

```sh
python3 FPGA/modelsim/run_regression.py --native-runtime "$HOME/intelFPGA/20.1"
```

The four stale wildcard benches now connect and independently check metadata.
Packet tests use seven words, six-word prefetch, final timestamp backpressure,
and discard-through-TLAST after overlong packets. Both explicit accumulator
benches now drive and check metadata. Existing signed-coordinate, capacity,
collision, overflow, reset and stall assertions remain enabled. Readout and
end-to-end DMA benches are included in the runner (eight-word RX, TKEEP/TLAST).
No DUT internals are initialized or forced. Payload checks are validity gated.

These replace September 29 four-word verification claims. Old screenshots and
wave views are historical illustrations, not evidence for the current protocol.
This is four-state RTL simulation, not Vitis compilation or board validation.
Full-configuration shared-vector stress and software evidence are documented in
`Development/Reports/voxel/` as those stages are completed.
