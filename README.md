# RF Mapping With Drone Swarm

This repository is organized as a drone-swarm research and development stack for cooperative RF-assisted mapping. The active, tested prototype is the ESP32 RSSI acquisition and offline probabilistic RF-mapping pipeline; the larger autonomy, hardware, visual mapping, distributed-comms, and base-station areas are scaffolded so future work has a clear home.

The RF layer is auxiliary sensing. Camera, IMU, VIO, SLAM, and flight-safety systems remain responsible for pose, metric geometry, and collision-critical decisions.

## Quick Start

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s Development/Tests -v
python rf_mapper.py plot Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv
```

The packaged source layout also supports:

```sh
python -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
python Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py --help
```

## Active Prototype

| Path | Purpose |
| --- | --- |
| `Mapping/RF_Mapping/rf_mapping/` | Python RF mapping package: data loading, calibration, inference, field models, observability, occupancy, simulation, and visualization |
| `Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py` | CLI implementation |
| `rf_mapper.py` | Backward-compatible root CLI/import shim |
| `rf_mapping/` | Compatibility import shim for running from a source checkout without setting `PYTHONPATH` |
| `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/` | Arduino ESP32 RSSI survey firmware and safe credential template |
| `Development/Datasets/examples/survey_output/` | Checked-in legacy 3 x 3 measured RSSI survey fixture |
| `Development/Datasets/examples/acquisition_metadata.example.json` | Acquisition metadata template |
| `Development/Datasets/calibration/calibration_samples.example.csv` | Open-space calibration example |
| `Development/Tests/unit/` | Standard-library `unittest` suite |
| `Docs/Design/prototype_workflow.md` | Detailed RF prototype workflow |
| `Docs/Architecture/system_overview.md` | Long-form system architecture and research direction |

## Repository Layout

| Directory | Responsibility |
| --- | --- |
| [Hardware/](Hardware/) | Physical system design and components: mechanical, electrical, power, sensors, BOMs, base and docking stations. |
| [ESP32_Code/](ESP32_Code/) | All firmware and code running directly on ESP32 devices, including low-level flight control, RF capture, and radio communication. |
| [Autonomy/](Autonomy/) | Higher-level autonomous flight, localization, navigation, planning, and mission behavior. |
| [Mapping/](Mapping/) | RF mapping, camera 3D mapping, environmental reconstruction, and sensor fusion. |
| [Swarm/](Swarm/) | Distributed communication, coordination, mapping, synchronization, and ground-station swarm management. |
| [FPGA/](FPGA/) | RTL, verification, interfaces, acceleration, constraints, and FPGA implementation. |
| [Development/](Development/) | Simulation, experiments, tests, datasets, and development utilities. |
| [Docs/](Docs/) | Architecture, design, research, and protocol documentation. |

Only implemented areas and documented planning boundaries have directories.
The Python package stays together under `Mapping/RF_Mapping/rf_mapping/` to
preserve its public imports, including the existing simulation and visualization
APIs. Root launchers, Python configuration, and `.github/` retain their
repository-wide roles.

## Current Status

Implemented:

- ESP32 scalar RSSI acquisition firmware
- Manual 2D survey workflow
- Measured RSSI heatmap generation
- RF acquisition metadata validation
- Robust open-space path-loss calibration
- Probabilistic RF field estimation
- Attenuation/obstacle evidence gating
- Synthetic RF experiments
- Unit test suite and CI workflow

Planned:

- CSI experiments after exact ESP32 board/chip support is confirmed
- Autonomous flight, VIO, SLAM, and collision avoidance
- Multi-agent communication and global map fusion
- 3D RF voxel mapping and base-station dashboards

See [Docs/Design/prototype_workflow.md](Docs/Design/prototype_workflow.md) for the detailed RF workflow and [Docs/Research/CSI_FOLLOW_ON.md](Docs/Research/CSI_FOLLOW_ON.md) for the CSI follow-on design.
