# RF mapping ModelSim project

Open **[rf_mapping.mpf](rf_mapping.mpf)** in ModelSim. It contains all five RTL
SystemVerilog modules, all five Verilog wrappers, and all seven testbench files,
organized into `RTL` and `Testbenches` folders. Source references are relative to
this directory. The compiled `work/` library is generated locally and ignored by Git.

## Run the regression

From the repository root, with `vsim`, `vlog`, and `vlib` on `PATH`:

```bash
python3 FPGA/modelsim/run_regression.py
```

On this machine, the installed PRoot launcher makes `vlog` incorrectly report
`unexpected end of source code`, even for a three-line smoke test. The following
verified command uses the **same installed ModelSim compiler**, invoked directly
with its private 32-bit ELF loader:

```bash
python3 FPGA/modelsim/run_regression.py --native-runtime "$HOME/intelFPGA/20.1"
```

This changes no vendor binaries or system libraries. The native runtime option
only affects compilation; simulation still uses `vsim`. On this installation,
use this command to recompile instead of the GUI's Compile menu.

The runner compiles all `rtl/*.sv`, `rtl/*.v`, and `tb/*.sv`, creates the project
if missing, then runs every testbench independently with seed `20260929`. Override
the seed with `--seed NUMBER`. A result passes only if ModelSim reports no
errors/fatals, the bench reaches its final PASS marker, and `$finish` is reached.
This is necessary because ModelSim can return exit code zero after `$fatal`.
There are both simulation-time watchdogs and a host timeout.

Outputs:

- [logs/results.json](logs/results.json): simulator version, seed, source list, and per-test results.
- `logs/compile.log` and `logs/<testbench>.log`: complete compile and simulation transcripts.
- `waves/<testbench>.wlf`: full recorded ModelSim waveform databases, including accessible internals.
- [VERIFICATION.md](VERIFICATION.md): coverage and the testbench repairs made for the current RTL.

## Review the waveforms

```bash
cd FPGA/modelsim
vsim -gui -do 'project open rf_mapping.mpf; do wave_views.do; rf_show voxel'
```

In the ModelSim Transcript, select any of the saved views:

```tcl
rf_show axis_passthrough
rf_show rf_packet_unpacker
rf_show voxel
rf_show voxel_lookup
rf_show voxel_accumulator
rf_show voxel_lookup collisions
rf_show voxel_accumulator overflow
rf_show voxel_accumulator stall
```

Views have readable signal labels, signed decimal coordinates/RSSI, explanatory
dividers, selected time ranges, and a cursor. Green traces show requests and blue
traces show results. Orange traces expose pipeline occupancy or hash probing.
The value column samples the active cursor; `Now` shows the end of the recording.
Payloads are meaningful only when the corresponding valid signal is asserted;
several RTL blocks intentionally leave payload registers unreset.

## Recreate screenshots

After a passing regression, run from this directory on Linux with an X11/Xwayland
display, ImageMagick's `import`, and `xwininfo` available:

```bash
vsim -gui -do 'project open rf_mapping.mpf; do capture_screenshots.do'
```

This captures the actual ModelSim Wave window into eight PNGs in
[`../waveform_screenshots`](../waveform_screenshots/README.md). It leaves the GUI
open. Keep only one ModelSim Wave window open during automated capture. On other
platforms, use the same `rf_show` views and the operating system's screenshot tool.

The project can be recreated from the current source inventory by closing it,
moving the existing `.mpf` aside, and running `vsim -c -do create_project.do` from
this directory. `create_project.do` uses ModelSim's project commands.
