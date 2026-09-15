# Repository Reorganization Verification

Prepared on 2026-09-14, before committing to local `main`.

## Scope and Baselines

The starting checkout already contained the earlier staged drone-swarm reorganization.
Its index snapshot was `40959bbaedf347a33a37f5feedc5ca89eb055c7b`; the last commit
was `d46f681`. This report distinguishes those two baselines.

All source files, tests, firmware, configuration, documentation, tracked datasets,
and the heatmap asset were inspected before moves. Imports, file operations,
`__file__`/working-directory assumptions, serial messages/includes, CLI defaults,
Markdown targets, setup examples, and CI commands were reviewed. No PlatformIO,
CMake, Make, shell/PowerShell script files, FPGA sources/testbenches, Vivado/TCL,
or XDC files were present.

The eight requested subsystem directories are present. Unimplemented areas have
planning READMEs; no empty directory taxonomy remains. Existing root launchers,
packaging, requirements, security/contribution policies, and GitHub CI retain
their repository-wide roles.

## File Moves and Dependencies

Every substantive move from the starting checkout is listed below. All used
`git mv`; no moved filename was changed.

| Old Path | New Path | References Reviewed/Updated |
| --- | --- | --- |
| `data/calibration/calibration_samples.example.csv` | `Development/Datasets/calibration/calibration_samples.example.csv` | test_calibration.py; test_cli.py; test_data.py; test_inference.py; test_legacy.py; operator copy/load commands |
| `data/examples/acquisition_metadata.example.json` | `Development/Datasets/examples/acquisition_metadata.example.json` | test_calibration.py; test_cli.py; test_data.py; test_inference.py; test_legacy.py; operator copy/load commands |
| `data/examples/survey_output/point_summary_20260831_184759.csv` | `Development/Datasets/examples/survey_output/point_summary_20260831_184759.csv` | test_calibration.py; test_cli.py; test_data.py; test_inference.py; test_legacy.py; operator copy/load commands |
| `data/examples/survey_output/raw_samples_20260831_184759.csv` | `Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv` | test_calibration.py; test_cli.py; test_data.py; test_inference.py; test_legacy.py; operator copy/load commands |
| `data/examples/survey_output/rssi_heatmap_20260831_184759.png` | `Development/Datasets/examples/survey_output/rssi_heatmap_20260831_184759.png` | test_calibration.py; test_cli.py; test_data.py; test_inference.py; test_legacy.py; operator copy/load commands |
| `docs/architecture/system_overview.md` | `Docs/Architecture/system_overview.md` | README links; operator and CSI links; embedded repository tree |
| `docs/rf_mapping/CSI_FOLLOW_ON.md` | `Docs/Research/CSI_FOLLOW_ON.md` | README.md; system_overview.md; prototype_workflow.md |
| `docs/rf_mapping/prototype_workflow.md` | `Docs/Design/prototype_workflow.md` | README.md; system_overview.md |
| `firmware/rf_sensor/esp32_rssi_mapper/esp32_rssi_mapper.ino` | `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/esp32_rssi_mapper.ino` | local wifi_credentials.h include; .gitignore; SECURITY.md; firmware setup commands |
| `firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.example.h` | `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.example.h` | local wifi_credentials.h include; .gitignore; SECURITY.md; firmware setup commands |
| `software/rf_mapping/__init__.py` | `Mapping/RF_Mapping/rf_mapping/__init__.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/artifacts.py` | `Mapping/RF_Mapping/rf_mapping/artifacts.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/calibration.py` | `Mapping/RF_Mapping/rf_mapping/calibration.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/cli/__init__.py` | `Mapping/RF_Mapping/rf_mapping/cli/__init__.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/cli/rf_mapper.py` | `Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/data.py` | `Mapping/RF_Mapping/rf_mapping/data.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/field_model.py` | `Mapping/RF_Mapping/rf_mapping/field_model.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/inference.py` | `Mapping/RF_Mapping/rf_mapping/inference.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/observability.py` | `Mapping/RF_Mapping/rf_mapping/observability.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/occupancy.py` | `Mapping/RF_Mapping/rf_mapping/occupancy.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/simulation.py` | `Mapping/RF_Mapping/rf_mapping/simulation.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `software/rf_mapping/visualization.py` | `Mapping/RF_Mapping/rf_mapping/visualization.py` | rf_mapper.py; rf_mapping/__init__.py; pyproject.toml; pytest.ini; test path bootstrap; CI; README; operator workflow |
| `tests/__init__.py` | `Development/Tests/__init__.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/__init__.py` | `Development/Tests/unit/__init__.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/_path.py` | `Development/Tests/unit/_path.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_calibration.py` | `Development/Tests/unit/test_calibration.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_cli.py` | `Development/Tests/unit/test_cli.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_data.py` | `Development/Tests/unit/test_data.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_field_model.py` | `Development/Tests/unit/test_field_model.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_inference.py` | `Development/Tests/unit/test_inference.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_legacy.py` | `Development/Tests/unit/test_legacy.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_observability.py` | `Development/Tests/unit/test_observability.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_occupancy.py` | `Development/Tests/unit/test_occupancy.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_simulation.py` | `Development/Tests/unit/test_simulation.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |
| `tests/unit/test_visualization.py` | `Development/Tests/unit/test_visualization.py` | unittest discovery; pytest.ini; CI; README; CONTRIBUTING.md; __file__ fixture references |

Package-internal references remain `rf_mapping.*` and relative imports such as
`.data`, `.calibration`, and `.occupancy`. Every Python runtime module,
including the CLI implementation, is byte-for-byte identical to the starting
index snapshot. Firmware and all five dataset/asset files are also byte-identical.

Directory operations were: the RF package into Mapping/RF_Mapping, the complete
Arduino sketch folder into ESP32_Code/RF_Capture/RSSI, tests into Development/Tests,
data into Development/Datasets, and the three existing documents into the
appropriate Docs subdirectories. Other previous directories contained only
empty placeholders.

### Original Committed Layout

For comparison with `d46f681`, before either staged reorganization:

| Original Path | Final Path |
| --- | --- |
| `README.md` (long-form architecture) | `Docs/Architecture/system_overview.md` |
| `rf_mapping_project/README.md` | `Docs/Design/prototype_workflow.md` |
| `rf_mapping_project/.gitignore` | Root `.gitignore` |
| `rf_mapping_project/requirements.txt` | Root `requirements.txt` |
| `rf_mapping_project/rf_mapper.py` | `Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py` |
| `rf_mapping_project/rf_mapping/*` | `Mapping/RF_Mapping/rf_mapping/*`, same filenames |
| `rf_mapping_project/tests/*` | `Development/Tests/unit/*`, same filenames |
| `rf_mapping_project/esp32_rssi_mapper/*` | `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/*`, same filenames |
| `rf_mapping_project/examples/acquisition_metadata.example.json` | `Development/Datasets/examples/acquisition_metadata.example.json` |
| `rf_mapping_project/examples/calibration_samples.example.csv` | `Development/Datasets/calibration/calibration_samples.example.csv` |
| `rf_mapping_project/survey_output/*` | `Development/Datasets/examples/survey_output/*`, same filenames |
| `rf_mapping_project/docs/CSI_FOLLOW_ON.md` | `Docs/Research/CSI_FOLLOW_ON.md` |

All 33 files from that commit have a destination. Its RF package, firmware,
datasets, and requirements match their original bytes. The CLI's only source
addition relative to that commit is the earlier seven-line direct-launch import
path bootstrap. Earlier root import/CLI entry points and test bootstrapping are
retained; no new runtime compatibility layer was added in this pass.

### Removed Empty Scaffolding

104 tracked zero-byte `.gitkeep` files from the starting snapshot were removed,
along with two ignored zero-byte placeholders at
`software/rf_mapping/calibration/.gitkeep` and `tools/calibration/.gitkeep`.
Only empty directories were pruned. No substantive file was deleted.

<details>
<summary>Complete list of removed tracked placeholder paths</summary>

- `configs/drones/.gitkeep`
- `configs/experiments/.gitkeep`
- `configs/missions/.gitkeep`
- `configs/sensors/.gitkeep`
- `configs/simulation/.gitkeep`
- `data/manifests/.gitkeep`
- `data/schemas/.gitkeep`
- `docs/camera_3d_mapping/.gitkeep`
- `docs/distributed_comms/.gitkeep`
- `docs/experiments/.gitkeep`
- `docs/flight/.gitkeep`
- `docs/hardware/.gitkeep`
- `docs/interfaces/.gitkeep`
- `docs/requirements/.gitkeep`
- `docs/safety/.gitkeep`
- `experiments/flight/.gitkeep`
- `experiments/notebooks/.gitkeep`
- `experiments/rf/.gitkeep`
- `experiments/templates/.gitkeep`
- `experiments/vision/.gitkeep`
- `firmware/flight_controller/.gitkeep`
- `firmware/fpga/bitstreams/.gitkeep`
- `firmware/fpga/constraints/.gitkeep`
- `firmware/fpga/drivers/.gitkeep`
- `firmware/fpga/ip/.gitkeep`
- `firmware/fpga/rtl/.gitkeep`
- `firmware/fpga/sim/.gitkeep`
- `firmware/motor_controller/.gitkeep`
- `firmware/radio_link/.gitkeep`
- `firmware/rf_sensor/esp32_csi_experiments/.gitkeep`
- `hardware/airframe/.gitkeep`
- `hardware/bom/.gitkeep`
- `hardware/electronics/base_station/.gitkeep`
- `hardware/electronics/camera_payload/.gitkeep`
- `hardware/electronics/flight_controller/.gitkeep`
- `hardware/electronics/fpga_payload/.gitkeep`
- `hardware/electronics/motor_controller/.gitkeep`
- `hardware/electronics/power_distribution/.gitkeep`
- `hardware/electronics/rf_payload/.gitkeep`
- `hardware/mechanical/.gitkeep`
- `hardware/pcb/.gitkeep`
- `hardware/test_fixtures/.gitkeep`
- `simulation/hitl/.gitkeep`
- `simulation/regression/.gitkeep`
- `simulation/sensor_models/camera/.gitkeep`
- `simulation/sensor_models/fpga/.gitkeep`
- `simulation/sensor_models/imu/.gitkeep`
- `simulation/sensor_models/rf/.gitkeep`
- `simulation/sitl/.gitkeep`
- `simulation/swarm_scenarios/.gitkeep`
- `simulation/vehicle_models/.gitkeep`
- `simulation/worlds/.gitkeep`
- `software/autonomous_flight/collision_avoidance/.gitkeep`
- `software/autonomous_flight/control_allocation/.gitkeep`
- `software/autonomous_flight/health_monitor/.gitkeep`
- `software/autonomous_flight/mission_manager/.gitkeep`
- `software/autonomous_flight/state_estimation/.gitkeep`
- `software/autonomous_flight/trajectory_planning/.gitkeep`
- `software/base_station/data_recorder/.gitkeep`
- `software/base_station/map_server/.gitkeep`
- `software/base_station/mission_control/.gitkeep`
- `software/base_station/swarm_dashboard/.gitkeep`
- `software/camera_3d_mapping/camera_calibration/.gitkeep`
- `software/camera_3d_mapping/dense_reconstruction/.gitkeep`
- `software/camera_3d_mapping/mesh_generation/.gitkeep`
- `software/camera_3d_mapping/multi_agent_sfm/.gitkeep`
- `software/camera_3d_mapping/sfm/.gitkeep`
- `software/camera_3d_mapping/slam/.gitkeep`
- `software/camera_3d_mapping/visual_inertial_odometry/.gitkeep`
- `software/common/.gitkeep`
- `software/distributed_comms/consensus/.gitkeep`
- `software/distributed_comms/mesh/.gitkeep`
- `software/distributed_comms/peer_discovery/.gitkeep`
- `software/distributed_comms/routing/.gitkeep`
- `software/distributed_comms/telemetry/.gitkeep`
- `software/distributed_comms/time_sync/.gitkeep`
- `software/global_mapping/frame_graph/.gitkeep`
- `software/global_mapping/map_fusion/.gitkeep`
- `software/global_mapping/pose_graph/.gitkeep`
- `software/global_mapping/world_model/.gitkeep`
- `software/interfaces/mavlink/.gitkeep`
- `software/interfaces/msg/.gitkeep`
- `software/interfaces/schemas/.gitkeep`
- `software/interfaces/srv/.gitkeep`
- `software/rf_mapping/acquisition/.gitkeep`
- `software/rf_mapping/channel_models/.gitkeep`
- `software/rf_mapping/csi/.gitkeep`
- `software/rf_mapping/field_model/.gitkeep`
- `software/rf_mapping/fusion/.gitkeep`
- `software/rf_mapping/localization/.gitkeep`
- `software/rf_mapping/observability/.gitkeep`
- `software/rf_mapping/rssi/.gitkeep`
- `software/rf_mapping/visualization/.gitkeep`
- `tests/fixtures/.gitkeep`
- `tests/flight_safety/.gitkeep`
- `tests/hardware_in_loop/.gitkeep`
- `tests/integration/.gitkeep`
- `tests/simulation/.gitkeep`
- `third_party/.gitkeep`
- `tools/ci/.gitkeep`
- `tools/dataset/.gitkeep`
- `tools/deployment/.gitkeep`
- `tools/flashing/.gitkeep`
- `tools/plotting/.gitkeep`

</details>

## Reference Changes

- `rf_mapper.py`: source search root now resolves to Mapping/RF_Mapping.
- `rf_mapping/__init__.py`: package search path now resolves to the moved package;
  its source-layout docstring was updated.
- `pyproject.toml`: setuptools discovery root changed to Mapping/RF_Mapping.
  Project name/version, dependencies, Python requirement, build requirements,
  and `rf-mapper` entry point are unchanged.
- `pytest.ini`: source and test roots updated.
- `Development/Tests/unit/_path.py`: repository parent depth increased from two
  to three and the package search root updated.
- `test_calibration.py`, `test_cli.py`, `test_data.py`, `test_inference.py`,
  `test_legacy.py`: repository parent depth and fixture locations updated.
  Test assertions are unchanged.
- `Development/__init__.py`: added only to preserve root-level unittest
  recursion. Without it, default discovery found zero tests after the move;
  with it, discovery finds the original 72.
- `.github/workflows/ci.yml`: compile and unittest discovery paths updated.
- `.gitignore` and `SECURITY.md`: ignored local ESP32 credential-header path updated.
- `README.md`, `CONTRIBUTING.md`, `prototype_workflow.md`, and
  `system_overview.md`: source, firmware, dataset, test, command, and relative
  document paths updated. Repository layout sections reflect the new structure.
  Windows and POSIX setup/usage instructions and scientific documentation remain.
- Eight subsystem READMEs document existing responsibilities and planned work.

All input and output path semantics remain unchanged: input/config paths come
from the caller, plotting writes beside its input CSV, and default survey,
inference, calibration, and synthetic output locations remain caller-relative.
Serial baud, commands, sample counts, CSV/JSON schemas, algorithms, and public
Python names are unchanged.

The complete line-level diff of existing files against the starting snapshot
appears in the appendix. Old paths there and in the inventory above are
intentional historical references.

## Validation Results

| Check | Result |
| --- | --- |
| Starting Python 3.14.6 unittest suite | PASS: 72 tests, 31.273 s |
| Post-move data-loading test checkpoint | PASS: 11 tests |
| Post-move `python3 -m unittest discover -s Development/Tests -v` | PASS: 72 tests, 16.377 s |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q` | PASS: 72 tests, 16.66 s; two expected missing-metadata warnings |
| Plain `python3 -m pytest -q` | Environment failure before collection: installed ROS launch_testing plugin requires missing lark. Disabling unrelated plugin autoload permits all project tests to pass. |
| Fresh Python 3.12.3 environment, `python -m unittest discover -v` | PASS: 72 tests, 16.132 s; validates root-level discovery and relocated imports |
| Python syntax/byte compilation | PASS: all runtime, launchers, and test sources on Python 3.14 and 3.12 |
| Module imports | PASS: root CLI and all 11 package submodules imported |
| CLI launch | PASS: root and direct implementation --help, plus all five subcommand help pages (12 invocations), from outside the repository |
| Serial utility | PASS: `python3 -m serial.tools.list_ports` launches |
| Measured plot + legacy inference | PASS: copied CSV remains unchanged; PNG outputs valid; no unsupported components emitted |
| Example calibration | PASS: moved CSV loads and calibration JSON is generated |
| Three documented default simulations | PASS: crossing rectangle, empty scene, and single-AP scene produce expected statuses |
| Simulated serial acquisition | PASS: PING/MEASURE exchange writes 200 v2 samples, valid metadata/calibration linkage, summary CSV, and heatmap |
| Wheel build | PASS: `python3 -m pip wheel . --no-deps --no-build-isolation` |
| Installed wheel CLI | PASS: wheel installed without dependency changes into temporary venv; `rf-mapper --help` runs outside checkout |
| File preservation | PASS: all 46 substantive starting files retained; all 33 original committed files accounted for |
| Runtime/data/firmware identity | PASS: Git blob comparisons against starting snapshot; original committed RF modules, firmware, datasets, and requirements also unchanged |
| Dependency specifications | PASS: requirements.txt and dependency/build versions unchanged |
| Local Markdown/image links | PASS: 36 parsed local targets resolve before adding this report |
| POSIX documentation syntax | PASS: 11 sh/bash blocks parsed with `bash -n` |
| CI configuration | PASS: YAML parsed; run-block shell syntax and new paths checked |
| Arduino layout/includes | PASS: matching sketch/folder basename retained; local header template and credential ignore checked |
| Existing heatmap | PASS: valid PNG, visually inspected, bytes preserved |
| Stale active path references | PASS: no obsolete source/test/firmware/docs/data paths outside intentional audit history |
| Git whitespace check | PASS: `git diff --check` |

The primary environment used Python 3.14.6, NumPy 2.4.6, Matplotlib 3.11.0,
and pyserial 3.5. A separate Python 3.12.3 venv installed the unchanged
requirements (NumPy 2.5.3, Matplotlib 3.11.2, pyserial 3.5). The system Python
lacks ensurepip, so the existing pip executable installed into that temporary
venv using `--python`; no system packages or repository dependency specifications
were changed.

Timing observations above are not a benchmark. No compilation stage or runtime
algorithm changed, and the moved package has the same source files. There is no
evidence of a build or test-time regression in these runs.

## Categorization Decisions

No files remain uncategorized.

The existing `rf_mapping.simulation` and `rf_mapping.visualization` modules stay
inside the RF package because they are exposed by its runtime CLI and public
imports. Moving them separately would change those interfaces or require new
compatibility code. Future independent development utilities belong under
Development; cross-sensor visualization can have its own Mapping area when it
exists.

The ESP32 sketch and template remain together. Splitting Wi-Fi setup, serial
messages, and RSSI capture into separate source modules would be a firmware
refactor, so the complete sketch belongs in RF_Capture/RSSI.

## Validation Limits and Remaining Risks

- Arduino CLI/PlatformIO and the exact ESP32 board target are unavailable.
  No hardware build, upload, physical RF capture, or real serial-device session
  was performed. The sketch is unchanged and its local include layout preserved.
- No FPGA project exists to lint or simulate. Icarus Verilog and Verilator are
  installed, but there are no RTL, testbench, XDC, or Vivado/TCL inputs.
- PowerShell is unavailable. Windows commands were inspected and paths updated;
  execution on Windows/macOS and hardware-specific USB drivers was not tested.
- GitHub-hosted CI was not dispatched; its local commands and configuration were
  validated. This task commits locally to main and does not push.
- Ten existing external research/documentation URLs were preserved; remote
  availability was not tested. All local documentation and asset links resolve.
- `plot` still writes derived artifacts beside its CSV. Smoke checks use copies
  so the tracked survey artifacts remain unchanged.
- The existing repository LICENSE placeholder is retained without modification.
- No existing workflow is known to be broken by this reorganization.

## Complete Existing-File Diff

This appendix records every move and changed reference relative to the starting
staged layout. Added subsystem planning READMEs and this report are described
above; the only additional source file is the unittest-discovery marker.

<details>
<summary>Path and reference diff (historical paths are intentional)</summary>

~~~~diff
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 2a38ed5..4eeabc9 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -18,5 +18,5 @@ jobs:
           python -m pip install -r requirements.txt
       - name: Compile Python
-        run: python -m compileall -q rf_mapper.py software tests
+        run: python -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
       - name: Run tests
-        run: python -m unittest discover -s tests -v
+        run: python -m unittest discover -s Development/Tests -v
diff --git a/.gitignore b/.gitignore
index 73ae141..22195e7 100644
--- a/.gitignore
+++ b/.gitignore
@@ -1,3 +1,3 @@
-firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.h
+ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h
 .venv/
 **/.venv/
diff --git a/CONTRIBUTING.md b/CONTRIBUTING.md
index 60ecb0d..29dd153 100644
--- a/CONTRIBUTING.md
+++ b/CONTRIBUTING.md
@@ -10,6 +10,6 @@ python3 -m venv .venv
 python -m pip install --upgrade pip
 python -m pip install -r requirements.txt
-python -m unittest discover -s tests -v
-python -m compileall -q rf_mapper.py software tests
+python -m unittest discover -s Development/Tests -v
+python -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
 ```

@@ -18,7 +18,7 @@ python -m compileall -q rf_mapper.py software tests
 - Keep RF-only evidence separate from collision-safe geometry claims.
 - Preserve raw measurement data and metadata needed for reproducibility.
-- Add tests for behavior changes in `software/rf_mapping/`.
+- Add tests for behavior changes in `Mapping/RF_Mapping/rf_mapping/`.
 - Keep generated outputs out of commits unless they are intentional fixtures in
-  `data/examples/`.
+  `Development/Datasets/examples/`.
 - Do not commit local credentials or board-specific assumptions that have not
   been verified on hardware.
diff --git a/data/calibration/calibration_samples.example.csv b/Development/Datasets/calibration/calibration_samples.example.csv
similarity index 100%
rename from data/calibration/calibration_samples.example.csv
rename to Development/Datasets/calibration/calibration_samples.example.csv
diff --git a/data/examples/acquisition_metadata.example.json b/Development/Datasets/examples/acquisition_metadata.example.json
similarity index 100%
rename from data/examples/acquisition_metadata.example.json
rename to Development/Datasets/examples/acquisition_metadata.example.json
diff --git a/data/examples/survey_output/point_summary_20260831_184759.csv b/Development/Datasets/examples/survey_output/point_summary_20260831_184759.csv
similarity index 100%
rename from data/examples/survey_output/point_summary_20260831_184759.csv
rename to Development/Datasets/examples/survey_output/point_summary_20260831_184759.csv
diff --git a/data/examples/survey_output/raw_samples_20260831_184759.csv b/Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv
similarity index 100%
rename from data/examples/survey_output/raw_samples_20260831_184759.csv
rename to Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv
diff --git a/data/examples/survey_output/rssi_heatmap_20260831_184759.png b/Development/Datasets/examples/survey_output/rssi_heatmap_20260831_184759.png
similarity index 100%
rename from data/examples/survey_output/rssi_heatmap_20260831_184759.png
rename to Development/Datasets/examples/survey_output/rssi_heatmap_20260831_184759.png
diff --git a/tests/__init__.py b/Development/Tests/__init__.py
similarity index 100%
rename from tests/__init__.py
rename to Development/Tests/__init__.py
diff --git a/tests/unit/__init__.py b/Development/Tests/unit/__init__.py
similarity index 100%
rename from tests/unit/__init__.py
rename to Development/Tests/unit/__init__.py
diff --git a/tests/unit/_path.py b/Development/Tests/unit/_path.py
similarity index 69%
rename from tests/unit/_path.py
rename to Development/Tests/unit/_path.py
index 89bdd2e..69c21f6 100644
--- a/tests/unit/_path.py
+++ b/Development/Tests/unit/_path.py
@@ -5,5 +5,5 @@ from pathlib import Path


-SOFTWARE_ROOT = Path(__file__).resolve().parents[2] / "software"
+SOFTWARE_ROOT = Path(__file__).resolve().parents[3] / "Mapping" / "RF_Mapping"
 software_path = str(SOFTWARE_ROOT)
 if software_path not in sys.path:
diff --git a/tests/unit/test_calibration.py b/Development/Tests/unit/test_calibration.py
similarity index 97%
rename from tests/unit/test_calibration.py
rename to Development/Tests/unit/test_calibration.py
index be719bc..aeb7cf4 100644
--- a/tests/unit/test_calibration.py
+++ b/Development/Tests/unit/test_calibration.py
@@ -22,6 +22,6 @@ class CalibrationTests(unittest.TestCase):
     def test_documented_example_is_valid_and_recoverable(self) -> None:
         example_path = (
-            Path(__file__).resolve().parents[2]
-            / "data/calibration/calibration_samples.example.csv"
+            Path(__file__).resolve().parents[3]
+            / "Development/Datasets/calibration/calibration_samples.example.csv"
         )
         result = fit_log_distance_calibration(load_calibration_csv(example_path))
diff --git a/tests/unit/test_cli.py b/Development/Tests/unit/test_cli.py
similarity index 98%
rename from tests/unit/test_cli.py
rename to Development/Tests/unit/test_cli.py
index 4dd0455..29fb5c0 100644
--- a/tests/unit/test_cli.py
+++ b/Development/Tests/unit/test_cli.py
@@ -19,6 +19,6 @@ class CommandLineTests(unittest.TestCase):
     def test_documented_acquisition_metadata_config_is_accepted(self) -> None:
         example_path = (
-            Path(__file__).resolve().parents[2]
-            / "data/examples/acquisition_metadata.example.json"
+            Path(__file__).resolve().parents[3]
+            / "Development/Datasets/examples/acquisition_metadata.example.json"
         )
         config = _load_acquisition_metadata_config(str(example_path))
diff --git a/tests/unit/test_data.py b/Development/Tests/unit/test_data.py
similarity index 98%
rename from tests/unit/test_data.py
rename to Development/Tests/unit/test_data.py
index 00d1282..ddf2a35 100644
--- a/tests/unit/test_data.py
+++ b/Development/Tests/unit/test_data.py
@@ -26,8 +26,8 @@ from rf_mapping.data import (


-REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
+REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
 CHECKED_IN_SURVEY = (
     REPOSITORY_ROOT
-    / "data/examples/survey_output/raw_samples_20260831_184759.csv"
+    / "Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv"
 )

diff --git a/tests/unit/test_field_model.py b/Development/Tests/unit/test_field_model.py
similarity index 100%
rename from tests/unit/test_field_model.py
rename to Development/Tests/unit/test_field_model.py
diff --git a/tests/unit/test_inference.py b/Development/Tests/unit/test_inference.py
similarity index 98%
rename from tests/unit/test_inference.py
rename to Development/Tests/unit/test_inference.py
index 8a6b2ac..e6734f9 100644
--- a/tests/unit/test_inference.py
+++ b/Development/Tests/unit/test_inference.py
@@ -17,8 +17,8 @@ from rf_mapping.simulation import SimulationConfig, generate_synthetic_dataset


-REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
+REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
 CHECKED_IN_SURVEY = (
     REPOSITORY_ROOT
-    / "data/examples/survey_output/raw_samples_20260831_184759.csv"
+    / "Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv"
 )

diff --git a/tests/unit/test_legacy.py b/Development/Tests/unit/test_legacy.py
similarity index 96%
rename from tests/unit/test_legacy.py
rename to Development/Tests/unit/test_legacy.py
index bd50639..6e89a1a 100644
--- a/tests/unit/test_legacy.py
+++ b/Development/Tests/unit/test_legacy.py
@@ -12,7 +12,7 @@ import rf_mapper


-PROJECT_ROOT = Path(__file__).resolve().parents[2]
+PROJECT_ROOT = Path(__file__).resolve().parents[3]
 LEGACY_RAW = (
-    PROJECT_ROOT / "data/examples/survey_output/raw_samples_20260831_184759.csv"
+    PROJECT_ROOT / "Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv"
 )

diff --git a/tests/unit/test_observability.py b/Development/Tests/unit/test_observability.py
similarity index 100%
rename from tests/unit/test_observability.py
rename to Development/Tests/unit/test_observability.py
diff --git a/tests/unit/test_occupancy.py b/Development/Tests/unit/test_occupancy.py
similarity index 100%
rename from tests/unit/test_occupancy.py
rename to Development/Tests/unit/test_occupancy.py
diff --git a/tests/unit/test_simulation.py b/Development/Tests/unit/test_simulation.py
similarity index 100%
rename from tests/unit/test_simulation.py
rename to Development/Tests/unit/test_simulation.py
diff --git a/tests/unit/test_visualization.py b/Development/Tests/unit/test_visualization.py
similarity index 100%
rename from tests/unit/test_visualization.py
rename to Development/Tests/unit/test_visualization.py
diff --git a/docs/architecture/system_overview.md b/Docs/Architecture/system_overview.md
similarity index 95%
rename from docs/architecture/system_overview.md
rename to Docs/Architecture/system_overview.md
index ae5b858..10d96d9 100644
--- a/docs/architecture/system_overview.md
+++ b/Docs/Architecture/system_overview.md
@@ -10,5 +10,5 @@ The long-term system is intended to produce two complementary representations of
 The RF system is an additional sensing layer. It is **not** intended to replace cameras, IMUs, VIO, SLAM, or other collision-critical geometric sensing.

-The current working implementation is in [`software/rf_mapping`](../../software/rf_mapping), with the operator workflow in [`docs/rf_mapping/prototype_workflow.md`](../rf_mapping/prototype_workflow.md).
+The current working implementation is in [`Mapping/RF_Mapping/rf_mapping`](../../Mapping/RF_Mapping/rf_mapping), with the operator workflow in [`Docs/Design/prototype_workflow.md`](../Design/prototype_workflow.md).

 ---
@@ -75,5 +75,5 @@ The current software extends that baseline with:
 The complete setup, calibration, collection, inference, validation, and troubleshooting workflow is documented in:

-[`docs/rf_mapping/prototype_workflow.md`](../rf_mapping/prototype_workflow.md)
+[`Docs/Design/prototype_workflow.md`](../Design/prototype_workflow.md)

 ---
@@ -499,5 +499,5 @@ CSI is a major planned research direction, but it must remain separate from the
 The proposed first CSI experiment is documented in:

-[`docs/rf_mapping/CSI_FOLLOW_ON.md`](../rf_mapping/CSI_FOLLOW_ON.md)
+[`Docs/Research/CSI_FOLLOW_ON.md`](../Research/CSI_FOLLOW_ON.md)

 The initial CSI goal is **not obstacle imaging**.
@@ -768,45 +768,30 @@ The project must not describe RSSI or CSI experiments as radar unless the sensin
 ```text
 RF-Mapping-with-Drone-Swarm-/
-│
 ├── README.md
 ├── LICENSE
-├── SECURITY.md
-├── CONTRIBUTING.md
-│
-├── docs/
-│   ├── architecture/
-│   ├── rf_mapping/
-│   ├── flight/
-│   ├── hardware/
-│   └── distributed_comms/
-│
-├── firmware/
-│   └── rf_sensor/
-│       └── esp32_rssi_mapper/
-│
-├── software/
-│   ├── autonomous_flight/
-│   ├── distributed_comms/
-│   ├── rf_mapping/
-│   ├── camera_3d_mapping/
-│   ├── global_mapping/
-│   └── base_station/
-│
-├── data/
-│   ├── examples/
-│   └── calibration/
-│
-├── simulation/
-├── experiments/
-├── hardware/
-├── tests/
-├── tools/
-├── configs/
-└── third_party/
+├── .gitignore
+├── .github/
+├── Hardware/
+├── ESP32_Code/
+│   └── RF_Capture/RSSI/esp32_rssi_mapper/
+├── Autonomy/
+├── Mapping/
+│   └── RF_Mapping/rf_mapping/
+├── Swarm/
+├── FPGA/
+├── Development/
+│   ├── Tests/unit/
+│   └── Datasets/
+│       ├── examples/
+│       └── calibration/
+└── Docs/
+    ├── Architecture/
+    ├── Design/
+    └── Research/
 ```

 For installation, firmware configuration, data collection, calibration, inference commands, simulation, validation, and troubleshooting, see:

-## [`docs/rf_mapping/prototype_workflow.md`](../rf_mapping/prototype_workflow.md)
+## [`Docs/Design/prototype_workflow.md`](../Design/prototype_workflow.md)

 ---
diff --git a/docs/rf_mapping/prototype_workflow.md b/Docs/Design/prototype_workflow.md
similarity index 91%
rename from docs/rf_mapping/prototype_workflow.md
rename to Docs/Design/prototype_workflow.md
index c04c764..1231a25 100644
--- a/docs/rf_mapping/prototype_workflow.md
+++ b/Docs/Design/prototype_workflow.md
@@ -49,21 +49,21 @@ hold yaw, pitch, and roll fixed or measure their effects deliberately.
 | Path | Purpose |
 | --- | --- |
-| `firmware/rf_sensor/esp32_rssi_mapper/esp32_rssi_mapper.ino` | Stable 115200-baud `PING`/`MEASURE,x,y` firmware; 50 RSSI samples at 10 Hz |
-| `firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.example.h` | Safe credential template |
+| `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/esp32_rssi_mapper.ino` | Stable 115200-baud `PING`/`MEASURE,x,y` firmware; 50 RSSI samples at 10 Hz |
+| `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.example.h` | Safe credential template |
 | `rf_mapper.py` | Backward-compatible root command-line entry point |
-| `software/rf_mapping/cli/rf_mapper.py` | Packaged CLI implementation |
-| `software/rf_mapping/artifacts.py` | Deterministic NPZ/JSON serialization and input hashing |
-| `software/rf_mapping/data.py` | Strict legacy/v2 loading, metadata checks, per-pass and robust statistics |
-| `software/rf_mapping/calibration.py` | Robust log-distance calibration and artifact validation |
-| `software/rf_mapping/field_model.py` | Path-loss-mean Gaussian-process residual field |
-| `software/rf_mapping/occupancy.py` | Exact 2D ray lengths, nonnegative MAP attenuation, bootstrap evidence |
-| `software/rf_mapping/observability.py` | Independent-link, transmitter, angle, conditioning, distance, and pass gates |
-| `software/rf_mapping/inference.py` | Auditable end-to-end inference and deterministic outputs |
-| `software/rf_mapping/simulation.py` | Deterministic empty/rectangle synthetic experiments and quantitative metrics |
-| `software/rf_mapping/visualization.py` | Six-panel audit figure |
-| `data/examples/` | Valid acquisition metadata template and measured survey fixture |
-| `data/calibration/` | Valid calibration CSV template |
-| `tests/unit/` | Standard-library `unittest` suite |
-| `docs/rf_mapping/CSI_FOLLOW_ON.md` | Board-gated CSI experiment design; no CSI firmware is claimed |
+| `Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py` | Packaged CLI implementation |
+| `Mapping/RF_Mapping/rf_mapping/artifacts.py` | Deterministic NPZ/JSON serialization and input hashing |
+| `Mapping/RF_Mapping/rf_mapping/data.py` | Strict legacy/v2 loading, metadata checks, per-pass and robust statistics |
+| `Mapping/RF_Mapping/rf_mapping/calibration.py` | Robust log-distance calibration and artifact validation |
+| `Mapping/RF_Mapping/rf_mapping/field_model.py` | Path-loss-mean Gaussian-process residual field |
+| `Mapping/RF_Mapping/rf_mapping/occupancy.py` | Exact 2D ray lengths, nonnegative MAP attenuation, bootstrap evidence |
+| `Mapping/RF_Mapping/rf_mapping/observability.py` | Independent-link, transmitter, angle, conditioning, distance, and pass gates |
+| `Mapping/RF_Mapping/rf_mapping/inference.py` | Auditable end-to-end inference and deterministic outputs |
+| `Mapping/RF_Mapping/rf_mapping/simulation.py` | Deterministic empty/rectangle synthetic experiments and quantitative metrics |
+| `Mapping/RF_Mapping/rf_mapping/visualization.py` | Six-panel audit figure |
+| `Development/Datasets/examples/` | Valid acquisition metadata template and measured survey fixture |
+| `Development/Datasets/calibration/` | Valid calibration CSV template |
+| `Development/Tests/unit/` | Standard-library `unittest` suite |
+| `Docs/Research/CSI_FOLLOW_ON.md` | Board-gated CSI experiment design; no CSI firmware is claimed |

 No dependency was added beyond NumPy, Matplotlib, and pyserial.
@@ -102,5 +102,5 @@ the checked-in artifacts untouched.

    ```powershell
-   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
+   .\.venv\Scripts\python.exe -m unittest discover -s Development/Tests -v
    ```

@@ -110,5 +110,5 @@ the checked-in artifacts untouched.
    ```powershell
    New-Item -ItemType Directory -Force smoke_output | Out-Null
-   Copy-Item .\data\examples\survey_output\raw_samples_20260831_184759.csv .\smoke_output\legacy.csv
+   Copy-Item .\Development\Datasets\examples\survey_output\raw_samples_20260831_184759.csv .\smoke_output\legacy.csv
    .\.venv\Scripts\python.exe rf_mapper.py plot .\smoke_output\legacy.csv
    .\.venv\Scripts\python.exe rf_mapper.py infer .\smoke_output\legacy.csv --grid-resolution-cm 5 --kernel-length-scale-cm 50 --seed 0 --output-dir .\smoke_output\legacy_inference
@@ -137,7 +137,7 @@ python3 -m venv .venv
 python -m pip install --upgrade pip
 python -m pip install -r requirements.txt
-python -m unittest discover -s tests -v
+python -m unittest discover -s Development/Tests -v
 mkdir -p smoke_output
-cp data/examples/survey_output/raw_samples_20260831_184759.csv smoke_output/legacy.csv
+cp Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv smoke_output/legacy.csv
 python rf_mapper.py plot smoke_output/legacy.csv
 python rf_mapper.py infer smoke_output/legacy.csv --grid-resolution-cm 5 --kernel-length-scale-cm 50 --seed 0 --output-dir smoke_output/legacy_inference
@@ -165,7 +165,7 @@ Create the local ignored header on Windows:

 ```powershell
-Copy-Item .\firmware\rf_sensor\esp32_rssi_mapper\wifi_credentials.example.h .\firmware\rf_sensor\esp32_rssi_mapper\wifi_credentials.h
-notepad .\firmware\rf_sensor\esp32_rssi_mapper\wifi_credentials.h
-git check-ignore .\firmware\rf_sensor\esp32_rssi_mapper\wifi_credentials.h
+Copy-Item .\ESP32_Code\RF_Capture\RSSI\esp32_rssi_mapper\wifi_credentials.example.h .\ESP32_Code\RF_Capture\RSSI\esp32_rssi_mapper\wifi_credentials.h
+notepad .\ESP32_Code\RF_Capture\RSSI\esp32_rssi_mapper\wifi_credentials.h
+git check-ignore .\ESP32_Code\RF_Capture\RSSI\esp32_rssi_mapper\wifi_credentials.h
 ```

@@ -173,7 +173,7 @@ Or on POSIX:

 ```sh
-cp firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.example.h firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.h
-${EDITOR:-vi} firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.h
-git check-ignore firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.h
+cp ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.example.h ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h
+${EDITOR:-vi} ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h
+git check-ignore ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h
 ```

@@ -181,5 +181,5 @@ Replace only `REPLACE_WITH_YOUR_HOTSPOT_NAME` and
 `REPLACE_WITH_YOUR_HOTSPOT_PASSWORD`. Never put either value in a dataset,
 metadata file, command line, log, issue, or commit. `git check-ignore` should
-print `firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.h`, confirming that the real file is
+print `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h`, confirming that the real file is
 ignored.

@@ -188,5 +188,5 @@ ignored.
 1. Read the exact board marking or provide a clear front/back photo. In Arduino
    IDE Boards Manager, install **esp32 by Espressif Systems**.
-2. Open `firmware/rf_sensor/esp32_rssi_mapper/esp32_rssi_mapper.ino`.
+2. Open `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/esp32_rssi_mapper.ino`.
 3. Choose **Tools > Board > [BOARD MATCHING THE PHYSICAL MARKING]**. This value
    is intentionally unresolved; do not assume C3, S3, XIAO, or another variant.
@@ -223,5 +223,5 @@ Copy and edit the metadata template:

 ```powershell
-Copy-Item .\data\examples\acquisition_metadata.example.json .\acquisition_metadata.json
+Copy-Item .\Development\Datasets\examples\acquisition_metadata.example.json .\acquisition_metadata.json
 notepad .\acquisition_metadata.json
 ```
@@ -287,5 +287,5 @@ real experiment:
 ```powershell
 New-Item -ItemType Directory -Force calibration | Out-Null
-Copy-Item .\data\calibration\calibration_samples.example.csv .\calibration\ap-main_samples.csv
+Copy-Item .\Development\Datasets\calibration\calibration_samples.example.csv .\calibration\ap-main_samples.csv
 notepad .\calibration\ap-main_samples.csv
 .\.venv\Scripts\python.exe rf_mapper.py calibrate .\calibration\ap-main_samples.csv --output .\calibration\ap-main.json
@@ -296,5 +296,5 @@ POSIX:
 ```sh
 mkdir -p calibration
-cp data/calibration/calibration_samples.example.csv calibration/ap-main_samples.csv
+cp Development/Datasets/calibration/calibration_samples.example.csv calibration/ap-main_samples.csv
 ${EDITOR:-vi} calibration/ap-main_samples.csv
 python rf_mapper.py calibrate calibration/ap-main_samples.csv --output calibration/ap-main.json
@@ -598,6 +598,6 @@ all synthetic APs identical transmit/propagation parameters.

 ```powershell
-.\.venv\Scripts\python.exe -m unittest discover -s tests -v
-.\.venv\Scripts\python.exe -m compileall -q rf_mapper.py software tests
+.\.venv\Scripts\python.exe -m unittest discover -s Development/Tests -v
+.\.venv\Scripts\python.exe -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
 ```

@@ -682,5 +682,5 @@ after that transform is established. The dock remains the origin/coordinator
 and heavier-compute point.

-CSI is intentionally not implemented. Read [the CSI follow-on design](CSI_FOLLOW_ON.md)
+CSI is intentionally not implemented. Read [the CSI follow-on design](../Research/CSI_FOLLOW_ON.md)
 after supplying the exact board marking/photo and toolchain. One PCB antenna and
 10 Hz scalar RSSI cannot implement RIM, SAR, through-wall imaging, or centimetre
diff --git a/docs/rf_mapping/CSI_FOLLOW_ON.md b/Docs/Research/CSI_FOLLOW_ON.md
similarity index 100%
rename from docs/rf_mapping/CSI_FOLLOW_ON.md
rename to Docs/Research/CSI_FOLLOW_ON.md
diff --git a/firmware/rf_sensor/esp32_rssi_mapper/esp32_rssi_mapper.ino b/ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/esp32_rssi_mapper.ino
similarity index 100%
rename from firmware/rf_sensor/esp32_rssi_mapper/esp32_rssi_mapper.ino
rename to ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/esp32_rssi_mapper.ino
diff --git a/firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.example.h b/ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.example.h
similarity index 100%
rename from firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.example.h
rename to ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.example.h
diff --git a/software/rf_mapping/__init__.py b/Mapping/RF_Mapping/rf_mapping/__init__.py
similarity index 100%
rename from software/rf_mapping/__init__.py
rename to Mapping/RF_Mapping/rf_mapping/__init__.py
diff --git a/software/rf_mapping/artifacts.py b/Mapping/RF_Mapping/rf_mapping/artifacts.py
similarity index 100%
rename from software/rf_mapping/artifacts.py
rename to Mapping/RF_Mapping/rf_mapping/artifacts.py
diff --git a/software/rf_mapping/calibration.py b/Mapping/RF_Mapping/rf_mapping/calibration.py
similarity index 100%
rename from software/rf_mapping/calibration.py
rename to Mapping/RF_Mapping/rf_mapping/calibration.py
diff --git a/software/rf_mapping/cli/__init__.py b/Mapping/RF_Mapping/rf_mapping/cli/__init__.py
similarity index 100%
rename from software/rf_mapping/cli/__init__.py
rename to Mapping/RF_Mapping/rf_mapping/cli/__init__.py
diff --git a/software/rf_mapping/cli/rf_mapper.py b/Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py
similarity index 100%
rename from software/rf_mapping/cli/rf_mapper.py
rename to Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py
diff --git a/software/rf_mapping/data.py b/Mapping/RF_Mapping/rf_mapping/data.py
similarity index 100%
rename from software/rf_mapping/data.py
rename to Mapping/RF_Mapping/rf_mapping/data.py
diff --git a/software/rf_mapping/field_model.py b/Mapping/RF_Mapping/rf_mapping/field_model.py
similarity index 100%
rename from software/rf_mapping/field_model.py
rename to Mapping/RF_Mapping/rf_mapping/field_model.py
diff --git a/software/rf_mapping/inference.py b/Mapping/RF_Mapping/rf_mapping/inference.py
similarity index 100%
rename from software/rf_mapping/inference.py
rename to Mapping/RF_Mapping/rf_mapping/inference.py
diff --git a/software/rf_mapping/observability.py b/Mapping/RF_Mapping/rf_mapping/observability.py
similarity index 100%
rename from software/rf_mapping/observability.py
rename to Mapping/RF_Mapping/rf_mapping/observability.py
diff --git a/software/rf_mapping/occupancy.py b/Mapping/RF_Mapping/rf_mapping/occupancy.py
similarity index 100%
rename from software/rf_mapping/occupancy.py
rename to Mapping/RF_Mapping/rf_mapping/occupancy.py
diff --git a/software/rf_mapping/simulation.py b/Mapping/RF_Mapping/rf_mapping/simulation.py
similarity index 100%
rename from software/rf_mapping/simulation.py
rename to Mapping/RF_Mapping/rf_mapping/simulation.py
diff --git a/software/rf_mapping/visualization.py b/Mapping/RF_Mapping/rf_mapping/visualization.py
similarity index 100%
rename from software/rf_mapping/visualization.py
rename to Mapping/RF_Mapping/rf_mapping/visualization.py
diff --git a/README.md b/README.md
index 16ecdfe..d0f1f6b 100644
--- a/README.md
+++ b/README.md
@@ -12,6 +12,6 @@ python3 -m venv .venv
 python -m pip install --upgrade pip
 python -m pip install -r requirements.txt
-python -m unittest discover -s tests -v
-python rf_mapper.py plot data/examples/survey_output/raw_samples_20260831_184759.csv
+python -m unittest discover -s Development/Tests -v
+python rf_mapper.py plot Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv
 ```

@@ -19,6 +19,6 @@ The packaged source layout also supports:

 ```sh
-python -m compileall -q rf_mapper.py software tests
-python software/rf_mapping/cli/rf_mapper.py --help
+python -m compileall -q rf_mapper.py rf_mapping Mapping Development/Tests
+python Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py --help
 ```

@@ -27,68 +27,34 @@ python software/rf_mapping/cli/rf_mapper.py --help
 | Path | Purpose |
 | --- | --- |
-| `software/rf_mapping/` | Python RF mapping package: data loading, calibration, inference, field models, observability, occupancy, simulation, and visualization |
-| `software/rf_mapping/cli/rf_mapper.py` | CLI implementation |
+| `Mapping/RF_Mapping/rf_mapping/` | Python RF mapping package: data loading, calibration, inference, field models, observability, occupancy, simulation, and visualization |
+| `Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py` | CLI implementation |
 | `rf_mapper.py` | Backward-compatible root CLI/import shim |
 | `rf_mapping/` | Compatibility import shim for running from a source checkout without setting `PYTHONPATH` |
-| `firmware/rf_sensor/esp32_rssi_mapper/` | Arduino ESP32 RSSI survey firmware and safe credential template |
-| `data/examples/survey_output/` | Checked-in legacy 3 x 3 measured RSSI survey fixture |
-| `data/examples/acquisition_metadata.example.json` | Acquisition metadata template |
-| `data/calibration/calibration_samples.example.csv` | Open-space calibration example |
-| `tests/unit/` | Standard-library `unittest` suite |
-| `docs/rf_mapping/prototype_workflow.md` | Detailed RF prototype workflow |
-| `docs/architecture/system_overview.md` | Long-form system architecture and research direction |
+| `ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/` | Arduino ESP32 RSSI survey firmware and safe credential template |
+| `Development/Datasets/examples/survey_output/` | Checked-in legacy 3 x 3 measured RSSI survey fixture |
+| `Development/Datasets/examples/acquisition_metadata.example.json` | Acquisition metadata template |
+| `Development/Datasets/calibration/calibration_samples.example.csv` | Open-space calibration example |
+| `Development/Tests/unit/` | Standard-library `unittest` suite |
+| `Docs/Design/prototype_workflow.md` | Detailed RF prototype workflow |
+| `Docs/Architecture/system_overview.md` | Long-form system architecture and research direction |

 ## Repository Layout

-```text
-.
-├── README.md
-├── LICENSE
-├── SECURITY.md
-├── CONTRIBUTING.md
-├── .github/
-├── docs/
-│   ├── architecture/
-│   ├── requirements/
-│   ├── safety/
-│   ├── interfaces/
-│   ├── hardware/
-│   ├── flight/
-│   ├── rf_mapping/
-│   ├── camera_3d_mapping/
-│   ├── distributed_comms/
-│   └── experiments/
-├── hardware/
-│   ├── airframe/
-│   ├── electronics/
-│   ├── mechanical/
-│   ├── pcb/
-│   ├── bom/
-│   └── test_fixtures/
-├── firmware/
-│   ├── flight_controller/
-│   ├── motor_controller/
-│   ├── rf_sensor/
-│   ├── radio_link/
-│   └── fpga/
-├── software/
-│   ├── interfaces/
-│   ├── common/
-│   ├── autonomous_flight/
-│   ├── distributed_comms/
-│   ├── rf_mapping/
-│   ├── camera_3d_mapping/
-│   ├── global_mapping/
-│   └── base_station/
-├── simulation/
-├── experiments/
-├── data/
-├── tests/
-├── tools/
-├── configs/
-└── third_party/
-```
-
-Detailed placeholder directories are intentionally tracked so new hardware, firmware, simulation, experiment, and software components can land without recreating the project taxonomy.
+| Directory | Responsibility |
+| --- | --- |
+| [Hardware/](Hardware/) | Physical system design and components: mechanical, electrical, power, sensors, BOMs, base and docking stations. |
+| [ESP32_Code/](ESP32_Code/) | All firmware and code running directly on ESP32 devices, including low-level flight control, RF capture, and radio communication. |
+| [Autonomy/](Autonomy/) | Higher-level autonomous flight, localization, navigation, planning, and mission behavior. |
+| [Mapping/](Mapping/) | RF mapping, camera 3D mapping, environmental reconstruction, and sensor fusion. |
+| [Swarm/](Swarm/) | Distributed communication, coordination, mapping, synchronization, and ground-station swarm management. |
+| [FPGA/](FPGA/) | RTL, verification, interfaces, acceleration, constraints, and FPGA implementation. |
+| [Development/](Development/) | Simulation, experiments, tests, datasets, and development utilities. |
+| [Docs/](Docs/) | Architecture, design, research, and protocol documentation. |
+
+Only implemented areas and documented planning boundaries have directories.
+The Python package stays together under `Mapping/RF_Mapping/rf_mapping/` to
+preserve its public imports, including the existing simulation and visualization
+APIs. Root launchers, Python configuration, and `.github/` retain their
+repository-wide roles.

 ## Current Status
@@ -113,3 +79,3 @@ Planned:
 - 3D RF voxel mapping and base-station dashboards

-See [docs/rf_mapping/prototype_workflow.md](docs/rf_mapping/prototype_workflow.md) for the detailed RF workflow and [docs/rf_mapping/CSI_FOLLOW_ON.md](docs/rf_mapping/CSI_FOLLOW_ON.md) for the CSI follow-on design.
+See [Docs/Design/prototype_workflow.md](Docs/Design/prototype_workflow.md) for the detailed RF workflow and [Docs/Research/CSI_FOLLOW_ON.md](Docs/Research/CSI_FOLLOW_ON.md) for the CSI follow-on design.
diff --git a/SECURITY.md b/SECURITY.md
index 357eb67..eb99b7d 100644
--- a/SECURITY.md
+++ b/SECURITY.md
@@ -19,3 +19,3 @@ privately and include:
 Never commit Wi-Fi credentials, API tokens, SSIDs, passwords, or raw private
 network identifiers. The ESP32 credential header is ignored at
-`firmware/rf_sensor/esp32_rssi_mapper/wifi_credentials.h`.
+`ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h`.
diff --git a/pyproject.toml b/pyproject.toml
index 1baa9a5..c134ecd 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -20,4 +20,4 @@ rf-mapper = "rf_mapping.cli.rf_mapper:main"

 [tool.setuptools.packages.find]
-where = ["software"]
+where = ["Mapping/RF_Mapping"]
 include = ["rf_mapping*"]
diff --git a/pytest.ini b/pytest.ini
index 2bd26da..e158cff 100644
--- a/pytest.ini
+++ b/pytest.ini
@@ -1,3 +1,3 @@
 [pytest]
-pythonpath = software
-testpaths = tests
+pythonpath = Mapping/RF_Mapping
+testpaths = Development/Tests
diff --git a/rf_mapper.py b/rf_mapper.py
index adc8ed8..0ee886a 100644
--- a/rf_mapper.py
+++ b/rf_mapper.py
@@ -5,5 +5,5 @@ from pathlib import Path


-SOFTWARE_ROOT = Path(__file__).resolve().parent / "software"
+SOFTWARE_ROOT = Path(__file__).resolve().parent / "Mapping" / "RF_Mapping"
 software_path = str(SOFTWARE_ROOT)
 if software_path not in sys.path:
diff --git a/rf_mapping/__init__.py b/rf_mapping/__init__.py
index d7b8f00..ca1a1b5 100644
--- a/rf_mapping/__init__.py
+++ b/rf_mapping/__init__.py
@@ -4,6 +4,6 @@ from pathlib import Path


-_SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "software" / "rf_mapping"
+_SOURCE_PACKAGE = Path(__file__).resolve().parents[1] / "Mapping" / "RF_Mapping" / "rf_mapping"
 __path__ = [str(_SOURCE_PACKAGE), *list(__path__)]

-__doc__ = "Compatibility package for the software/rf_mapping source layout."
+__doc__ = "Compatibility package for the Mapping/RF_Mapping/rf_mapping source layout."
~~~~

</details>
