# Reproducible voxel verification

Run from repository root after `python3 -m pip install -e ./Mapping/RF_Mapping`.

```sh
python3 Development/Tests/voxel/check_contract.py
python3 -m unittest discover -s Development/Tests/voxel -p 'test_host.py' -v
python3 Development/Tests/voxel/run_suite.py --mode quick --rtl
python3 Development/Tests/voxel/run_suite.py --mode stress --rtl
python3 Development/Tests/voxel/run_suite.py --mode soak --build /tmp/voxel-soak
python3 FPGA/modelsim/run_regression.py --native-runtime "$HOME/intelFPGA/20.1"
python3 FPGA/modelsim/run_regression.py --native-runtime "$HOME/intelFPGA/20.1" \
  --only tb_voxel_shared_vectors --seed 1 --no-stalls --no-waves
```

Quick uses 10,000 host observations; stress uses seeds 1–10 × 100,000 host
observations and (with `--rtl`) 10 × 10,000 RTL observations; soak uses seed 42 ×
1,000,000 host observations. The seeded Python model uses integer floor and a
dictionary independent of RTL hashing and C mirror implementation. It streams
15 hex words per row: seven input words followed by eight expected RX words.
The same vectors drive C and full-size four-state RTL. RTL also independently
checks handshakes, valid data, retention, lengths/TLAST/TKEEP and accounting.
Reduced accumulator count widths occur only in dedicated testbench configurations.

Host execution compiles with strict warnings, ASan and UBSan. Mock DMA schedules
arrival, TX completion and RX completion independently; output data becomes
CPU-visible only at invalidate. Both cache padding and ordering are asserted.
The actual `zybo_main.c` adapter is separately included in a mocked BSP test in
legacy and SDT modes; this does not substitute for a Vitis target build.

The C harness feeds actual versioned serial frames to the application, exercises
queues/map/export, and writes binary output. Python independently validates every
result and snapshot against regenerated golden vectors, including coordinates,
exact statistics, fractional mean and metadata, then uses the visualization
parser/map. Unit tests render sparse cubes at extreme separated coordinates,
exercise partial serial reads/writes with mocked ports, lost response deadlines,
pose expiry/wrap/reboot, frame corruption and linker-map placement guards.

The fault suite covers RX/TX start failures, DMA errors, timeout, wrong RX length,
invalid slots/flags/counts, wrong metadata, duplicate/stale results, overflow
nonmutation, full queues, stopped admission, serial/session errors and output
consumer disconnect. Existing RTL benches cover constructed hash collisions,
capacity rejection followed by existing-key updates, negative boundaries and
integer extremes, malformed short/long frames, missing TLAST, reset during
partial/pending work, initialization and narrow-counter saturation.

The mock fixture has a fixed static size; the application uses no malloc/free.
The runner records `/usr/bin/time` peak RSS for C and checks Python parser/map RSS
growth after 10,000 observations stays below 16 MiB. Vector generation, hashing,
wire parsing and expected-result checking are streamed with bounded buffers;
raw logs grow on disk intentionally. Do not run two suites in the same build
directory, or two RTL runs in the same ModelSim work/log directory concurrently.

Each run rewrites its report as incomplete before execution, then records command,
source/vector SHA-256, seeds, counts, durations, compiler/Python/simulator versions
and PASS/FAIL. Exceptions, assertions, compiler warnings, sanitizer findings,
simulator errors/fatals, missing final PASS, missing $finish or timeout are failures.
There is no old-PASS fallback. ModelSim's zero exit after $fatal is explicitly
handled by the regression runner. Generated work files stay in /tmp or ignored
ModelSim paths; concise JSON evidence is retained in Development/Reports/voxel.
