# RF Mapping With Drone Swarm

This repository is organized as a drone-swarm research and development stack for cooperative RF-assisted mapping. The active, tested prototype is the ESP32 RSSI acquisition and offline probabilistic RF-mapping pipeline; the larger autonomy, hardware, visual mapping, distributed-comms, and base-station areas are scaffolded so future work has a clear home.

The RF layer is auxiliary sensing. Camera, IMU, VIO, SLAM, and flight-safety systems remain responsible for pose, metric geometry, and collision-critical decisions.

## Quick Start

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./Mapping/RF_Mapping
python -m unittest discover -s Development/Tests/RF_Mapping -v
rf-mapper --help
```

The packaged source layout also supports:

```sh
python -m compileall -q rf_mapper.py Mapping/RF_Mapping/src Development/Tests
python -m rf_mapping.cli.rf_mapper --help
```

## Active Prototype

The [RF mapping subsystem](Mapping/RF_Mapping/README.md) documents the host
package, CLI, example plotting and calibration, datasets, and tests. It consumes
measurements from the [ESP32 acquisition firmware](ESP32_Code/README.md).
The root `python rf_mapper.py` launcher remains available after installation.
See the [system architecture](Docs/Architecture/system_overview.md) for how
these components fit into the complete drone swarm.

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
The Python package stays together under `Mapping/RF_Mapping/src/rf_mapping/` to
preserve its public imports, including the existing simulation and visualization
APIs. RF Python build metadata lives in `Mapping/RF_Mapping/pyproject.toml`;
the root test configuration and `.github/` coordinate repository validation.

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

See [Docs/Design/RF_Mapping/prototype_workflow.md](Docs/Design/RF_Mapping/prototype_workflow.md) for the detailed RF workflow and [Docs/Research/RF_Mapping/CSI_FOLLOW_ON.md](Docs/Research/RF_Mapping/CSI_FOLLOW_ON.md) for the CSI follow-on design.
