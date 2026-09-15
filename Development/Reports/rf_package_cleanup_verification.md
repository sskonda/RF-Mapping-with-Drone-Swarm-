# RF Package Cleanup Verification

Prepared 2026-09-14 before committing to local main. Baseline: `345ac23`.
`git pull --ff-only origin main` completed with "Already up to date"; the
starting worktree was clean. No push is part of this cleanup.

The functional migration is commit `f94bfe9`; this audit and its Development
index link form the second logical commit.

## Scope and Dependency Review

Reviewed the complete tracked tree, RF source and tests, packaging/configuration,
root/subsystem documentation, ESP32 sketch/template, CI and the preceding audit.
This is a packaging/path migration, not an algorithm refactor. The move table
records old path -> new path -> dependents identified during inspection.

Runtime graph (unchanged): console/module/root launcher -> CLI -> data,
calibration, inference or simulation. Calibration -> data; inference -> artifacts,
calibration, data, field_model, observability, occupancy, visualization;
simulation -> artifacts, calibration, observability, occupancy. NumPy,
Matplotlib and pyserial requirements are unchanged. CLI inputs and generated
outputs remain caller-relative; plotting still writes beside its input CSV.
Tests locate repository fixtures relative to their own file, not the cwd.

No CMake, Makefile, PlatformIO project, standalone shell/PowerShell scripts,
FPGA RTL, TCL, XDC or FPGA source lists exist in this baseline. Shell commands
are in CI and documentation. Firmware includes WiFi.h and the ignored local
wifi_credentials.h beside the unchanged sketch.

## Final Tracked Tree

Caches, build output and temporary validation environments are omitted.
No empty scaffolding is added.

```text
RF-Mapping-with-Drone-Swarm-/
|-- README.md
|-- LICENSE
|-- .gitignore
|-- CONTRIBUTING.md
|-- SECURITY.md
|-- pytest.ini
|-- requirements.txt
|-- rf_mapper.py
|-- .github/
|   `-- workflows/
|       `-- ci.yml
|-- Hardware/
|   `-- README.md
|-- ESP32_Code/
|   |-- README.md
|   `-- RF_Capture/
|       `-- RSSI/
|           `-- esp32_rssi_mapper/
|               |-- esp32_rssi_mapper.ino
|               `-- wifi_credentials.example.h
|-- Autonomy/
|   `-- README.md
|-- Mapping/
|   |-- README.md
|   `-- RF_Mapping/
|       |-- LICENSE
|       |-- README.md
|       |-- pyproject.toml
|       `-- src/
|           `-- rf_mapping/
|               |-- __init__.py
|               |-- artifacts.py
|               |-- calibration.py
|               |-- cli/
|               |   |-- __init__.py
|               |   `-- rf_mapper.py
|               |-- data.py
|               |-- field_model.py
|               |-- inference.py
|               |-- observability.py
|               |-- occupancy.py
|               |-- simulation.py
|               `-- visualization.py
|-- Swarm/
|   `-- README.md
|-- FPGA/
|   `-- README.md
|-- Development/
|   |-- Datasets/
|   |   `-- RF_Mapping/
|   |       |-- Acquisition_Examples/
|   |       |   `-- acquisition_metadata.example.json
|   |       |-- Calibration/
|   |       |   `-- calibration_samples.example.csv
|   |       `-- Measured_Surveys/
|   |           `-- Legacy_3x3/
|   |               |-- point_summary_20260831_184759.csv
|   |               |-- raw_samples_20260831_184759.csv
|   |               `-- rssi_heatmap_20260831_184759.png
|   |-- README.md
|   |-- Reports/
|   |   |-- reorganization_verification.md
|   |   `-- rf_package_cleanup_verification.md
|   `-- Tests/
|       |-- RF_Mapping/
|       |   |-- __init__.py
|       |   |-- test_calibration.py
|       |   |-- test_cli.py
|       |   |-- test_data.py
|       |   |-- test_field_model.py
|       |   |-- test_inference.py
|       |   |-- test_legacy.py
|       |   |-- test_observability.py
|       |   |-- test_occupancy.py
|       |   |-- test_simulation.py
|       |   `-- test_visualization.py
|       `-- __init__.py
`-- Docs/
    |-- Architecture/
    |   `-- system_overview.md
    |-- Design/
    |   `-- RF_Mapping/
    |       `-- prototype_workflow.md
    |-- README.md
    `-- Research/
        `-- RF_Mapping/
            `-- CSI_FOLLOW_ON.md
```

## Every Move

All 32 file moves used git mv. Filenames were preserved.

| Old path | New path | Dependents/references |
| --- | --- | --- |
| `Development/Datasets/calibration/calibration_samples.example.csv` | `Development/Datasets/RF_Mapping/Calibration/calibration_samples.example.csv` | test_calibration; calibration CLI examples |
| `Development/Datasets/examples/acquisition_metadata.example.json` | `Development/Datasets/RF_Mapping/Acquisition_Examples/acquisition_metadata.example.json` | test_cli; survey metadata CLI examples |
| `Development/Datasets/examples/survey_output/point_summary_20260831_184759.csv` | `Development/Datasets/RF_Mapping/Measured_Surveys/Legacy_3x3/point_summary_20260831_184759.csv` | Measured survey fixture, preserved beside raw CSV |
| `Development/Datasets/examples/survey_output/raw_samples_20260831_184759.csv` | `Development/Datasets/RF_Mapping/Measured_Surveys/Legacy_3x3/raw_samples_20260831_184759.csv` | test_data, test_inference, test_legacy; plot/infer examples |
| `Development/Datasets/examples/survey_output/rssi_heatmap_20260831_184759.png` | `Development/Datasets/RF_Mapping/Measured_Surveys/Legacy_3x3/rssi_heatmap_20260831_184759.png` | Measured survey fixture, preserved beside raw CSV |
| `Development/Tests/unit/__init__.py` | `Development/Tests/RF_Mapping/__init__.py` | Test-package discovery; bootstrap import removed |
| `Development/Tests/unit/test_calibration.py` | `Development/Tests/RF_Mapping/test_calibration.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_cli.py` | `Development/Tests/RF_Mapping/test_cli.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_data.py` | `Development/Tests/RF_Mapping/test_data.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_field_model.py` | `Development/Tests/RF_Mapping/test_field_model.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_inference.py` | `Development/Tests/RF_Mapping/test_inference.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_legacy.py` | `Development/Tests/RF_Mapping/test_legacy.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_observability.py` | `Development/Tests/RF_Mapping/test_observability.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_occupancy.py` | `Development/Tests/RF_Mapping/test_occupancy.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_simulation.py` | `Development/Tests/RF_Mapping/test_simulation.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Development/Tests/unit/test_visualization.py` | `Development/Tests/RF_Mapping/test_visualization.py` | Explicit unittest discovery, pytest.ini, CI; fixture/import changes below |
| `Docs/Design/prototype_workflow.md` | `Docs/Design/RF_Mapping/prototype_workflow.md` | Root, Mapping, Development, ESP32 and Docs READMEs; system overview |
| `Docs/Design/reorganization_verification.md` | `Development/Reports/reorganization_verification.md` | Docs/Development indexes; archival report retains historical references |
| `Docs/Research/CSI_FOLLOW_ON.md` | `Docs/Research/RF_Mapping/CSI_FOLLOW_ON.md` | Root, ESP32 and Docs READMEs; system overview; operator workflow |
| `Mapping/RF_Mapping/rf_mapping/__init__.py` | `Mapping/RF_Mapping/src/rf_mapping/__init__.py` | All rf_mapping imports; package discovery; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/artifacts.py` | `Mapping/RF_Mapping/src/rf_mapping/artifacts.py` | inference, simulation; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/calibration.py` | `Mapping/RF_Mapping/src/rf_mapping/calibration.py` | CLI survey/calibrate, inference, simulation, tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/cli/__init__.py` | `Mapping/RF_Mapping/src/rf_mapping/cli/__init__.py` | CLI entry point and tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/cli/rf_mapper.py` | `Mapping/RF_Mapping/src/rf_mapping/cli/rf_mapper.py` | rf-mapper entry point, module/root launchers, CLI/legacy tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/data.py` | `Mapping/RF_Mapping/src/rf_mapping/data.py` | CLI, calibration, inference, tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/field_model.py` | `Mapping/RF_Mapping/src/rf_mapping/field_model.py` | inference, field-model tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/inference.py` | `Mapping/RF_Mapping/src/rf_mapping/inference.py` | CLI infer, inference tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/observability.py` | `Mapping/RF_Mapping/src/rf_mapping/observability.py` | inference, simulation, tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/occupancy.py` | `Mapping/RF_Mapping/src/rf_mapping/occupancy.py` | inference, simulation, tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/simulation.py` | `Mapping/RF_Mapping/src/rf_mapping/simulation.py` | CLI simulate, simulation/inference tests; package/workflow documentation |
| `Mapping/RF_Mapping/rf_mapping/visualization.py` | `Mapping/RF_Mapping/src/rf_mapping/visualization.py` | inference, visualization tests; package/workflow documentation |
| `pyproject.toml` | `Mapping/RF_Mapping/pyproject.toml` | pip editable/regular installs, wheel/sdist, CLI entry point, CI, setup docs |

## Removed Compatibility and Path Hacks

- Deleted root `rf_mapping/__init__.py`, including custom `__path__` redirection.
- Deleted `Development/Tests/unit/_path.py` and its imports from the test
  package marker and eight test modules.
- Deleted `Development/__init__.py`; explicit test discovery replaces it.
- Removed `sys.path.insert` bootstrap from the root launcher and canonical CLI.
- Removed pytest's `pythonpath` override.
- Root `rf_mapper.py` now imports only canonical CLI main and exits with its
  result. Its migration-era dynamic re-export loop was removed; the two tests
  using it now import `rf_mapping.cli.rf_mapper` directly.
- No replacement shim, symlink, duplicate source package or path mutation added.

## Packaging and Reference Changes

| Location | Necessary change |
| --- | --- |
| RF pyproject | Project metadata moved to subsystem; setuptools discovery changed from Mapping/RF_Mapping to src. Name/version/dependency constraints/build backend/entry point unchanged. |
| RF README and LICENSE | New subsystem instructions and byte-identical distribution copy of root LICENSE, so wheel/sdist builds are self-contained. |
| Root launcher | Minimal installed-package launcher; installation now required for source checkout use. |
| Tests: calibration, CLI, data, inference, legacy | Updated concrete calibration, acquisition and survey fixture paths; same repository-root parent depth. |
| Tests: CLI and legacy | Imports changed from root launcher exports to canonical CLI module. |
| Other RF tests and test marker | Bootstrap imports removed; assertions and algorithms unchanged. |
| pytest.ini | Select Development/Tests/RF_Mapping, without injected package path. |
| CI | Editable subsystem install plus pytest; new source/test paths; both test runners; wheel build; console/module help from /tmp. |
| .gitignore | Ignore subsystem build/ and dist/ output; local credential ignore retained. |
| Root README | System-level overview and setup retained; RF usage details linked to subsystem README; obsolete compatibility-package claims removed. |
| CONTRIBUTING and Development README | Editable installation, subsystem test discovery, compile/build commands and dataset ownership. |
| Mapping and ESP32 READMEs | Canonical subsystem and RF design/research links. |
| Docs README and system overview | RF-specific documentation links/tree and development-audit location. |
| RF operator workflow | Source/fixture/doc paths and installation/test commands updated, including PowerShell paths. Existing protocol, setup and usage content preserved. |
| Historical reorganization report | Moved byte-for-byte; historical old paths intentionally not rewritten. |

The five RF fixture files retain their bytes. "Legacy_3x3" describes the existing
450-sample, nine-position measured survey; it does not invent acquisition
metadata. Runtime survey_output remains a valid unchanged CLI output default,
not the permanent fixture directory.

## Validation Commands and Results

Temporary artifacts were confined to /tmp. The primary Python 3.14 environments
used system-site-packages to reuse installed dependencies; isolated imports
(`-I`) and a separate wheel environment prevented checkout/package shims from
masking errors. Python 3.12 was also checked in its separate environment.

| Check | Result |
| --- | --- |
| Baseline unittest discover -s Development/Tests -v | 72 passed, 16.610 s |
| Baseline pytest -q, unrelated plugin autoload disabled | 72 passed, 15.93 s |
| After package move: CLI tests | 7 passed |
| After dataset/test moves: data tests | 11 passed |
| Editable Python 3.14 unittest, explicit RF discovery | 72 passed, 39.835 s |
| Editable Python 3.14 pytest | 72 passed, 39.86 s |
| Wheel Python 3.14 unittest from /tmp | 72 passed, 38.086 s |
| Wheel Python 3.14 pytest from /tmp | 72 passed, 38.85 s |
| Editable Python 3.12 unittest | 72 passed, 27.452 s |
| Editable Python 3.12 pytest, normal plugin discovery with -I | 72 passed, 27.31 s |
| compileall on source, launcher and tests | Passed on Python 3.14 and 3.12 |
| Package plus every RF module import from /tmp | Passed; editable resolves src, wheel resolves its site-packages |
| Editable installation | Passed on both Python versions |
| Isolated pip wheel build | Passed |
| setuptools sdist, then isolated wheel build from archive in /tmp | Passed; rebuilt wheel contents exactly match direct wheel contents |
| Wheel contents | One rf_mapping package; source bytes and license match; no Development package |
| Root/direct-source/module/console --help and five subcommands | All 24 invocations passed outside checkout |
| python -m serial.tools.list_ports | Launch passed outside checkout |
| Legacy CSV plot and infer | Passed; source CSV unchanged, valid PNGs, uncalibrated_inference_disabled and no components |
| Calibration example | Passed; artifact generated |
| Three default simulation CLI scenarios | Passed: crossing rectangle, empty crossing, single-AP rectangle retain expected evidence statuses |
| Mock serial survey -> v2 CSV/metadata -> visualization | Passed, 200 rows, 115200 baud, 50 samples per point |
| Markdown/local image links | All 52 parsed local targets resolve, including the final audit/index; historical diff blocks are not active links |
| Documentation POSIX blocks and CI run blocks | bash -n passed; CI YAML parsed |
| Arduino folder/include/template/ignore checks | Passed; .ino basename matches folder, header template remains adjacent |
| Baseline file accounting | All 56 starting files accounted for: 53 retained, only 3 packaging/test helpers removed |
| Byte/AST comparison | All RF algorithms, five datasets, firmware/header and historical report preserved; test class bodies match after fixture-path normalization |
| Packaging metadata comparison | Exact match except setuptools source root |
| Active stale-path and path-hack scans | Clean; migration reports retain historical paths intentionally |
| git diff --check and staged diff check | Passed; final diff limited to moves, packaging, import/path cleanup, CI and documentation |

Representative commands actually executed (environment paths abbreviated):

```sh
python -m pip install -e ./Mapping/RF_Mapping --no-deps --no-build-isolation
python -I -m unittest discover -s Development/Tests/RF_Mapping -v
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -I -m pytest -q
python -I -m compileall -q rf_mapper.py Mapping/RF_Mapping/src Development/Tests
python -m pip wheel ./Mapping/RF_Mapping --no-deps --wheel-dir /tmp/rf-package-cleanup.Xj3CPj/dist
git diff --check
git diff --cached --check
```

The wheel environment installed the resulting .whl with pip --no-deps, then ran
both test commands from /tmp with an absolute test-directory argument. It also
ran all help variants, serial listing, plot/infer/calibrate/simulate commands and
the mocked serial workflow. The subsystem sdist was produced by
setuptools.build_meta.build_sdist and rebuilt with pip wheel from /tmp.
Temporary audit scripts compared baseline Git blobs, normalized test ASTs,
wheel entries, local Markdown targets and command syntax.

Python 3.14 used NumPy 2.4.6 / Matplotlib 3.11.0 / pytest 9.0.3.
Python 3.12.3 used its existing NumPy 2.5.3 / Matplotlib 3.11.2, with pytest
9.1.1 installed as a validation tool. Project dependency constraints did not change.
The baseline environment's unrelated ROS pytest plugin requires missing lark;
plugin autoload was disabled for the 3.14 baseline/final runs only.
The 3.12 isolated run needed no such override. Missing-metadata warnings remain
expected scientific behavior. Timings above include concurrent validation
processes and are not a performance comparison.

## Decisions and Remaining Risks

- Keep public rf_mapping.simulation in the canonical package: CLI and tests
  depend on it. No Development/Simulation scaffolding or compatibility shim.
- Keep root requirements.txt unchanged as the existing runtime dependency list.
  It does not install the project; documented development setup installs the
  subsystem itself.
- Checkout users must run the documented editable install. Importing arbitrary
  CLI helpers from root rf_mapper is replaced by the canonical CLI module;
  repository consumers were migrated, with no evidence of another required
  external compatibility contract.
- No files remain uncategorized. No substantive implementation or data was
  deleted. Root system-level folder naming is unchanged.
- ESP32 build/upload/live radio collection were not validated: Arduino/PlatformIO
  tooling and the exact board target are unavailable. Mock serial is not a
  hardware test. Firmware/header bytes are unchanged.
- No FPGA/C/C++ host build or simulator testbench exists to run. Vivado is absent;
  available HDL linters have no project inputs. No FPGA path was changed.
- PowerShell execution/parser checks were unavailable (pwsh absent); Windows
  path references were reviewed and their POSIX equivalents exercised.
- External reference URLs were not availability-tested. Local links were checked.
  GitHub-hosted CI itself was not run; its commands and Python 3.12 tests were
  validated locally. Python 3.10/3.11 and real Windows/macOS were not run.
- Existing table-form license metadata triggers a setuptools deprecation warning.
  License policy and build dependency versions were deliberately not changed.
  The distribution LICENSE copy must stay synchronized with root LICENSE.
- Existing credential-history exposure remains documented in the operator
  workflow; this cleanup neither rewrites history nor changes security policy.

The [preceding reorganization audit](reorganization_verification.md) is preserved
as historical evidence, not current setup guidance.
