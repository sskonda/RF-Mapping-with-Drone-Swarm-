# RF Mapping

Host-side RF acquisition, calibration, probabilistic field estimation, attenuation
evidence, and visualization for the drone swarm project.

## Scope

The current RSSI workflow collects scalar Wi-Fi measurements from an
[ESP32 Arduino sketch](../../ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/),
associates them with manually supplied coordinates, and produces measured maps
or offline inference with uncertainty and observability checks.

This is not SLAM, wall reconstruction, or collision-safe free-space sensing.
Camera/IMU geometry remains responsible for navigation. Future cross-sensor
fusion belongs to the planned Mapping/Sensor_Fusion area; no fusion
implementation is present yet.

CSI is a future controlled experiment, pending confirmed hardware/toolchain
support. See the [CSI research plan](../../Docs/Research/RF_Mapping/CSI_FOLLOW_ON.md).

## Package

`pyproject.toml` owns this Python distribution.
`src/rf_mapping/` is the only rf_mapping package and contains data validation,
calibration, field models, inference, occupancy, observability, artifact helpers,
visualization, simulation, and `cli/rf_mapper.py`.

`rf_mapping.simulation` remains here because the public simulate CLI and tests
import it. Moving it to Development would break that API or require another
shim. Standalone future simulation infrastructure can live in Development.

The local LICENSE is a byte-identical distribution copy of the repository
LICENSE so source distributions and wheels can be built independently.

## Installation

From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ./Mapping/RF_Mapping
```

For a regular installation, omit `-e`. From this subsystem directory use
`python -m pip install -e .`. Editable installation resolves imports to this
same src package; no PYTHONPATH setup or import-path bootstrap is needed.

## CLI

```sh
rf-mapper --help
python -m rf_mapping.cli.rf_mapper --help
```

Commands are `survey`, `plot`, `calibrate`, `infer`, and `simulate`.
The repository-root `python rf_mapper.py` launcher remains available after
installation. Inputs and generated outputs retain their caller-relative paths;
plotting writes beside its input CSV.

Example from the repository root, preserving the checked-in survey:

```sh
mkdir -p smoke_output
cp Development/Datasets/RF_Mapping/Measured_Surveys/Legacy_3x3/raw_samples_20260831_184759.csv smoke_output/legacy.csv
rf-mapper plot smoke_output/legacy.csv
rf-mapper calibrate Development/Datasets/RF_Mapping/Calibration/calibration_samples.example.csv --output smoke_output/calibration.json
```

The [operator workflow](../../Docs/Design/RF_Mapping/prototype_workflow.md) covers metadata,
hardware setup, serial collection, inference, and interpretation in detail.

## Tests and Builds

From the repository root after installation:

```sh
python -m unittest discover -s Development/Tests/RF_Mapping -v
python -m pip install pytest
python -m pytest -q
python -m compileall -q Mapping/RF_Mapping/src Development/Tests rf_mapper.py
python -m pip wheel ./Mapping/RF_Mapping --no-deps --wheel-dir /tmp/rf-mapping-wheels
```

Use explicit unittest discovery; Development is an organizational directory.
Pytest uses the root configuration to select the RF suite. Both runners import
the installed package. Tests can also run against a wheel installation.

## Datasets

The checked-in RF fixtures include an acquisition metadata template, a
calibration CSV, and a legacy measured 3 x 3 survey with 450 scalar RSSI samples.
The survey lacks metadata/calibration needed for obstacle claims.

- [Acquisition example](../../Development/Datasets/RF_Mapping/Acquisition_Examples/acquisition_metadata.example.json)
- [Calibration example](../../Development/Datasets/RF_Mapping/Calibration/calibration_samples.example.csv)
- [Measured survey](../../Development/Datasets/RF_Mapping/Measured_Surveys/Legacy_3x3/)

See the [system architecture](../../Docs/Architecture/system_overview.md) for the
relationship to autonomy, swarm coordination, and geometric mapping.
