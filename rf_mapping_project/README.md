# Probabilistic RF-assisted indoor mapping

This repository preserves the original manual ESP32 RSSI survey and adds an
offline, reproducible RF-field and attenuation-evidence prototype. It is
**probabilistic RF-assisted mapping**, not full SLAM: the program receives known
manual coordinates and does not jointly estimate pose, perform loop closure, or
optimize a pose graph.

The safety boundary is strict:

- camera plus IMU/VIO/SfM supplies pose, metric geometry, and collision-critical
  free space;
- synchronized Wi-Fi measurements form an auxiliary RF layer that may reveal
  attenuation boundaries;
- a future dock/base station can provide home/origin, coordination, clock
  reference, and heavier computation for a sub-250-gram drone swarm;
- RF-only unknown or apparently clear space is never navigation-safe free space.

The original `survey` and `plot` commands and legacy CSV schema remain
supported. `plot` still draws only measured cells with no interpolation. The
new `infer` command separates **Measured RSSI**, **Estimated RF posterior mean**,
**Posterior standard deviation**, data/link support, excess attenuation, and
gated obstacle/attenuation evidence.

## Repository baseline and present limits

The pre-change checkout was verified on 2026-09-03: `main` and `origin/main`
were at `5e9b538`, with one earlier title-only commit. The checked-in successful
run contains 450 scalar samples: one pass, 50 samples at each of nine positions
on a 3 x 3 grid over 100 cm x 100 cm. Its point medians span approximately -25
to -56 dBm.

That dataset is a valid measured coverage map. It has no stored AP position,
calibration, receiver height/orientation, pose uncertainty, or crossing links.
The supported inference result is therefore
`uncalibrated_inference_disabled`/insufficient obstacle observability: a broad
exploratory RF field can be displayed, but no wall polygon, obstacle location,
or dimensions can be claimed. A 5 cm display grid adds pixels, not physical
measurements.

The exact ESP32 board/chip and antenna configuration are still unknown. The
firmware uses `WiFi.h` and targets the generic Arduino ESP32 API, but a board
selection cannot be asserted until the marking or a clear board photo is
available. A PCB trace antenna is directional, so every controlled trial must
hold yaw, pitch, and roll fixed or measure their effects deliberately.

## Files

| Path | Purpose |
| --- | --- |
| `esp32_rssi_mapper/esp32_rssi_mapper.ino` | Stable 115200-baud `PING`/`MEASURE,x,y` firmware; 50 RSSI samples at 10 Hz |
| `esp32_rssi_mapper/wifi_credentials.example.h` | Safe credential template |
| `rf_mapper.py` | Backward-compatible command-line entry point |
| `rf_mapping/artifacts.py` | Deterministic NPZ/JSON serialization and input hashing |
| `rf_mapping/data.py` | Strict legacy/v2 loading, metadata checks, per-pass and robust statistics |
| `rf_mapping/calibration.py` | Robust log-distance calibration and artifact validation |
| `rf_mapping/field_model.py` | Path-loss-mean Gaussian-process residual field |
| `rf_mapping/occupancy.py` | Exact 2D ray lengths, nonnegative MAP attenuation, bootstrap evidence |
| `rf_mapping/observability.py` | Independent-link, transmitter, angle, conditioning, distance, and pass gates |
| `rf_mapping/inference.py` | Auditable end-to-end inference and deterministic outputs |
| `rf_mapping/simulation.py` | Deterministic empty/rectangle synthetic experiments and quantitative metrics |
| `rf_mapping/visualization.py` | Six-panel audit figure |
| `examples/` | Valid calibration CSV and acquisition metadata templates |
| `tests/` | Standard-library `unittest` suite |
| `docs/CSI_FOLLOW_ON.md` | Board-gated CSI experiment design; no CSI firmware is claimed |

No dependency was added beyond NumPy, Matplotlib, and pyserial.

## Prerequisites

- Windows 10/11 PowerShell is the primary operator workflow. The offline CLI
  also supports current Linux and macOS POSIX shells.
- Python 3.10 through 3.12, 64-bit, with `venv` and `pip`.
- For physical collection: an ESP32-family board with 2.4 GHz Wi-Fi, a data USB
  cable, a fixed 2.4 GHz AP/hotspot, tape/fixture and measuring tools, and the
  exact board/chip marking.
- Arduino IDE 2.x with the Espressif Arduino-ESP32 3.x board package is the
  targeted firmware toolchain. The sketch uses stable `WiFi.h` APIs, but it has
  not been hardware-compiled in this checkout because the exact board target is
  unavailable. Select the board entry matching the physical marking; use
  **ESP32 Dev Module** only when that generic target is actually correct.

## Start here: clean clone to generated outputs on Windows

This hardware-free workflow is the shortest complete check. It creates a
measured heatmap and an exploratory inference from a copied legacy CSV, leaving
the checked-in artifacts untouched.

1. Clone, enter the project, and create the environment:

   ```powershell
   git clone https://github.com/sskonda/RF-Mapping-with-Drone-Swarm-.git
   Set-Location .\RF-Mapping-with-Drone-Swarm-\rf_mapping_project
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Run all tests:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

3. Copy the legacy input, render measured data, then run deterministic
   exploratory inference:

   ```powershell
   New-Item -ItemType Directory -Force smoke_output | Out-Null
   Copy-Item .\survey_output\raw_samples_20260831_184759.csv .\smoke_output\legacy.csv
   .\.venv\Scripts\python.exe rf_mapper.py plot .\smoke_output\legacy.csv
   .\.venv\Scripts\python.exe rf_mapper.py infer .\smoke_output\legacy.csv --grid-resolution-cm 5 --kernel-length-scale-cm 50 --seed 0 --output-dir .\smoke_output\legacy_inference
   ```

Expected conclusion:

```text
Inference status: uncalibrated_inference_disabled
Potential attenuation components: 0
Supported conclusion: no obstacle polygon or dimensions can be claimed.
```

The measured outputs are `smoke_output\legacy_point_summary.csv` and
`smoke_output\legacy_rssi_heatmap.png`. The six-panel output is
`smoke_output\legacy_inference\inference.png`; its report explicitly records
missing metadata/calibration and zero observable obstacle cells.

## Equivalent POSIX setup and smoke test

```sh
git clone https://github.com/sskonda/RF-Mapping-with-Drone-Swarm-.git
cd RF-Mapping-with-Drone-Swarm-/rf_mapping_project
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
mkdir -p smoke_output
cp survey_output/raw_samples_20260831_184759.csv smoke_output/legacy.csv
python rf_mapper.py plot smoke_output/legacy.csv
python rf_mapper.py infer smoke_output/legacy.csv --grid-resolution-cm 5 --kernel-length-scale-cm 50 --seed 0 --output-dir smoke_output/legacy_inference
```

On Windows, activation is optional; the documentation deliberately invokes
`.\.venv\Scripts\python.exe` directly so PowerShell execution-policy settings
cannot block the workflow. If desired, activate with:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

## Secure firmware setup

The hotspot credential formerly tracked in Git must be treated as exposed.
Rotate the hotspot password before using this repository again. The current
tree deletes the real header, tracks only placeholders, and ignores the local
header. Purging the old value from Git history is a separate destructive
history rewrite requiring explicit approval and coordinated force-push; this
project does not perform it automatically.

Create the local ignored header on Windows:

```powershell
Copy-Item .\esp32_rssi_mapper\wifi_credentials.example.h .\esp32_rssi_mapper\wifi_credentials.h
notepad .\esp32_rssi_mapper\wifi_credentials.h
git check-ignore .\esp32_rssi_mapper\wifi_credentials.h
```

Or on POSIX:

```sh
cp esp32_rssi_mapper/wifi_credentials.example.h esp32_rssi_mapper/wifi_credentials.h
${EDITOR:-vi} esp32_rssi_mapper/wifi_credentials.h
git check-ignore esp32_rssi_mapper/wifi_credentials.h
```

Replace only `REPLACE_WITH_YOUR_HOTSPOT_NAME` and
`REPLACE_WITH_YOUR_HOTSPOT_PASSWORD`. Never put either value in a dataset,
metadata file, command line, log, issue, or commit. `git check-ignore` should
print `esp32_rssi_mapper/wifi_credentials.h`, confirming that the real file is
ignored.

### Upload and serial check

1. Read the exact board marking or provide a clear front/back photo. In Arduino
   IDE Boards Manager, install **esp32 by Espressif Systems**.
2. Open `esp32_rssi_mapper/esp32_rssi_mapper.ino`.
3. Choose **Tools > Board > [BOARD MATCHING THE PHYSICAL MARKING]**. This value
   is intentionally unresolved; do not assume C3, S3, XIAO, or another variant.
4. Connect the data USB cable. In Windows Device Manager, expand **Ports (COM &
   LPT)** and note the port that appears, for example `[YOUR_COM_PORT] = COM5`.
   Choose it under **Tools > Port**.
5. Leave upload speed at the selected board package's supported default and
   click **Upload**. Upload baud and application serial baud are separate.
6. If upload stalls at `Connecting...`, use the board's documented BOOT/RESET
   procedure; for many generic boards, hold **BOOT**, begin upload, then release
   it when writing starts. Do not assume this sequence for an unidentified
   board.
7. Open Serial Monitor at exactly **115200 baud**. A successful startup is:

   ```text
   STATUS,CONNECTING
   STATUS,CONNECTED,6,-50
   READY
   ```

   Channel/RSSI values vary; network identifiers are deliberately not printed.
8. Send `PING`; expect `READY`. Close Serial Monitor before Python opens the
   port. Only one process can own a serial port.

## Coordinate and metadata conventions

The unchanged physical convention is a right-handed floor frame measured in
centimetres in the CSV: choose `(0,0)` once, +x and +y along the marked room
axes, and +z upward. CLI width/height describe `0..width` and `0..height` and
must be exact multiples of point spacing. Rich rows record yaw about +z, pitch
about +y, and roll about +x in degrees. Keep the PCB antenna orientation fixed.

Copy and edit the metadata template:

```powershell
Copy-Item .\examples\acquisition_metadata.example.json .\acquisition_metadata.json
notepad .\acquisition_metadata.json
```

Replace the exact board/chip marking, antenna orientation description, channel,
bandwidth, observed PHY mode, pose uncertainty, privacy-preserving AP hash (or
remove that optional field), environment/trial labels, and notes. Do not add
SSID, password, token, or
credential keys: the loader rejects them recursively. The sidecar schema checks
units, UTC timestamps, finite pose/covariance, unique AP IDs and complete 3D AP
positions, channel ranges, sample counts, CSV schema, and SHA-256 linkage.

Legacy raw CSV columns are unchanged:

```text
pass_index,x_cm,y_cm,sample_index,device_time_ms,rssi_dbm
```

When complete pose/AP arguments are supplied, `survey` writes version 2 rows:

```text
pass_index,x_cm,y_cm,sample_index,device_time_ms,rssi_dbm,host_time_utc,host_monotonic_ns,packet_sequence,ap_id,z_cm,yaw_deg,pitch_deg,roll_deg
```

The JSON sidecar adds run UUID, UTC start/finish, units, received/expected/lost
sample counts, CSI/noise-floor availability, dwell/rate, pose source and
uncertainty, AP position/ID, hardware/antenna/channel metadata, environment
labels, notes, and calibration file/version/hash. Old CSVs load with an explicit
metadata-unavailable warning; no defaults are fabricated.

## Open-space calibration

Use an unobstructed controlled sweep with known 3D transmitter-receiver
distances, fixed height and orientation, the same hardware/channel as the
survey, at least three distinct distances, and preferably three passes. Every
pass must cover the same distances so time drift is not confounded with range.
Keep raw samples; do not enter only hand-selected averages.

The first three CSV columns are mandatory and ordered exactly:

```text
distance_m,rssi_dbm,pass_index
```

Optional columns are `antenna_id`, `antenna_orientation`, `ap_id`,
`bandwidth_mhz`, `board_model`, `bssid_hash`, `channel`, `chip_model`,
`environment_label`, `phy_mode`, `receiver_height_cm`,
`transmitter_height_cm`, and `trial_label`. Every optional value must be present
and constant throughout one file. A valid row is:

```csv
1.0,-38.2,1,ap-main,REPLACE_WITH_EXACT_BOARD_MARKING,REPLACE_WITH_EXACT_CHIP,pcb_trace,onboard-antenna-1,fixed_yaw_pitch_roll_zero,6,20,REPLACE_WITH_OBSERVED_PHY,100,100,controlled_empty_space,open_space_sweep
```

The three core columns are enough to fit and inspect a field model. Shape
claims additionally require matching board/chip, antenna type/ID/orientation,
channel/bandwidth/PHY, and receiver/transmitter-height metadata; missing fields
remain an explicit observability-gate failure.

Use the complete runnable example, replacing its hardware placeholders before a
real experiment:

```powershell
New-Item -ItemType Directory -Force calibration | Out-Null
Copy-Item .\examples\calibration_samples.example.csv .\calibration\ap-main_samples.csv
notepad .\calibration\ap-main_samples.csv
.\.venv\Scripts\python.exe rf_mapper.py calibrate .\calibration\ap-main_samples.csv --output .\calibration\ap-main.json
```

POSIX:

```sh
mkdir -p calibration
cp examples/calibration_samples.example.csv calibration/ap-main_samples.csv
${EDITOR:-vi} calibration/ap-main_samples.csv
python rf_mapper.py calibrate calibration/ap-main_samples.csv --output calibration/ap-main.json
```

The supplied numeric example deterministically reports approximately:

```text
P0=-37.950 dBm at 1.000 m, n=1.9965, residual sigma=0.252 dB
Huber IRLS converged=True in 5 iterations; down-weighted 1/15 samples.
```

The model is

`P(d) = P0 - 10 n log10(d/d0) + epsilon`, with Gaussian residuals. Deterministic
Huber iteratively reweighted least squares reduces gross-outlier leverage and
saves P0, `n`, residual/within-pass/between-pass noise, fitting range, hardware
metadata, input hash, weights, residuals, R-squared, robust-versus-OLS
sensitivity, convergence, and whether between-pass drift was observable. A
non-positive `n`, singular sweep, inconsistent pass distances, or unconverged
fit is rejected. Material trials may be stored separately; the code contains no
universal wall-loss constants.

The generated JSON schema is version `1.0`: `model` stores `P0`, `n`, and `d0`;
`noise` stores residual, within-pass, and between-pass terms; `fit_range_m`
stores calibrated bounds; `input` stores the CSV hash/count and metadata;
`optimizer` stores Huber settings/convergence; `diagnostics` stores residuals,
weights, errors, R-squared, and pass means; and `outlier_sensitivity` compares
the robust fit with OLS. `load_calibration` validates every required field and
rejects non-finite or contradictory values. The command above creates a valid,
complete example at `calibration/ap-main.json`.

Calibration options:

| Argument | Meaning |
| --- | --- |
| `calibration_csv` | Input with the required first three columns |
| `--output PATH` | New calibration JSON; required and never allowed to equal the source CSV |
| `--reference-distance-m 1` | Reference distance `d0` |
| `--huber-delta 1.345` | Standardized Huber cutoff |
| `--max-iterations 100` | IRLS iteration limit |
| `--tolerance 1e-10` | Relative convergence tolerance |
| `--overwrite` | Permit replacing an existing output JSON, never the source CSV |

## Collect a version 2 survey

Find and release the COM port first:

```powershell
Get-CimInstance Win32_SerialPort | Format-Table DeviceID,Description
```

Close Arduino Serial Monitor, Arduino Serial Plotter, other Python processes,
terminal programs, and vendor tools using `[YOUR_COM_PORT]`. If Windows still
raises `PermissionError(13)`, disconnect/reconnect the board, confirm the port
number again, and use Microsoft Process Explorer's **Find Handle or DLL** search
for the COM name to identify the owner.

Example with realistic placeholders visibly marked:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py survey --port [YOUR_COM_PORT] --width-cm 200 --height-cm 200 --spacing-cm 20 --passes 3 --ap-id ap-main --ap-x-cm 0 --ap-y-cm 100 --ap-z-cm 100 --receiver-z-cm 100 --yaw-deg 0 --pitch-deg 0 --roll-deg 0 --pose-source manual --metadata-config .\acquisition_metadata.json --calibration-file .\calibration\ap-main.json --output-dir .\survey_output --show
```

PowerShell does not interpret `[YOUR_COM_PORT]` as a real port: replace it with
`COM5` or the observed value. POSIX uses the same options with a real device such
as `/dev/ttyUSB0` or `/dev/cu.usbserial-...`; serial permissions may require the
platform's device-access group.

POSIX collection example (replace `/dev/ttyUSB0` with the detected device):

```sh
python rf_mapper.py survey --port /dev/ttyUSB0 --width-cm 200 --height-cm 200 --spacing-cm 20 --passes 3 --ap-id ap-main --ap-x-cm 0 --ap-y-cm 100 --ap-z-cm 100 --receiver-z-cm 100 --yaw-deg 0 --pitch-deg 0 --roll-deg 0 --pose-source manual --metadata-config acquisition_metadata.json --calibration-file calibration/ap-main.json --output-dir survey_output --show
```

At each prompt, place the receiver at the displayed coordinate and fixed
height/orientation, leave the direct path, then press Enter. Collection takes
about five seconds per point. Enter `s` to skip or `q` to finish a partial run.
Pass 1 follows the serpentine path and even passes reverse it, exposing some
time-order drift rather than silently pooling it.

Survey options:

| Argument | Meaning |
| --- | --- |
| `--port` | Serial device; omit to choose from detected ports |
| `--width-cm`, `--height-cm` | Inclusive `0..extent` rectangle; positive exact spacing multiples |
| `--spacing-cm` | Physical point spacing, not plot resolution |
| `--passes` | Full-grid repetitions; default 1, use at least 3 for inference trials |
| `--output-dir` | Destination; default `survey_output` |
| `--title` | Measured heatmap title; default `Measured RSSI` |
| `--ap-x-cm`, `--ap-y-cm` | AP floor coordinates; both or neither |
| `--ap-id` | Stable privacy-preserving ID, never an SSID |
| `--ap-z-cm` | AP height |
| `--receiver-z-cm` | Receiver height |
| `--yaw-deg`, `--pitch-deg`, `--roll-deg` | Fixed antenna orientation |
| `--pose-source` | `manual`, `VIO`, or another truthful source label |
| `--metadata-config` | Hardware/channel/pose-uncertainty/environment JSON |
| `--calibration-file` | Valid artifact whose version/hash is recorded |
| `--show` | Open the figure after saving |

Supplying any new AP/3D pose field activates v2 rows and requires all AP xyz,
receiver z, orientation, and AP ID. Omitting them preserves the legacy format.

Each run writes, without modifying its raw source:

- `raw_samples_TIMESTAMP.csv`: every accepted sample;
- `survey_metadata_TIMESTAMP.json`: the versioned provenance sidecar;
- `point_summary_TIMESTAMP.csv`: legacy pooled point summary for the measured
  view (inference separately retains per-pass/outlier/drift diagnostics);
- `rssi_heatmap_TIMESTAMP.png`: no-interpolation **Measured RSSI** heatmap.

## Rebuild a measured map

```powershell
.\.venv\Scripts\python.exe rf_mapper.py plot .\survey_output\raw_samples_20260904_123456_123456.csv --show
```

```sh
python rf_mapper.py plot survey_output/raw_samples_20260904_123456_123456.csv --show
```

For a multi-AP v2 CSV, add `--ap-id ap-main`; the AP ID is hashed in derived
filenames. `--title`, `--ap-x-cm`, and `--ap-y-cm` affect display only. `plot`
never interpolates: each colored cell is based on samples actually recorded at
that coordinate.

## Run offline inference

One calibrated survey:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py infer .\survey_output\raw_samples_20260904_123456_123456.csv --metadata .\survey_output\survey_metadata_20260904_123456_123456.json --calibration .\calibration\ap-main.json --field-ap-id ap-main --grid-resolution-cm 10 --kernel-length-scale-cm 50 --seed 0 --output-dir .\inference_output
```

```sh
python rf_mapper.py infer survey_output/raw_samples_20260904_123456_123456.csv --metadata survey_output/survey_metadata_20260904_123456_123456.json --calibration calibration/ap-main.json --field-ap-id ap-main --grid-resolution-cm 10 --kernel-length-scale-cm 50 --seed 0 --output-dir inference_output
```

Replace the example timestamp with the matching suffix printed by `survey`.

Use `--show` to open the figure and `--overwrite` only when intentionally
replacing the three derived files in the output directory. Inputs are never
overwritten.

Inference options and defaults:

| Argument | Meaning |
| --- | --- |
| `raw_csv [raw_csv ...]` | One or more legacy/v2 survey files |
| `--metadata PATH` | One sidecar per CSV, repeated in the same order |
| `--calibration PATH` | Repeated per independently calibrated AP |
| `--field-ap-id ID` | AP whose receiver samples drive the displayed GP field; first sorted ID by default |
| `--output-dir inference_output` | Destination for PNG, NPZ, and JSON |
| `--grid-resolution-cm 10` | Display/inverse-grid cell size; cannot create information |
| `--kernel-length-scale-cm 50` | Fixed squared-exponential GP correlation length |
| `--gp-signal-std-db 6` | GP residual prior standard deviation |
| `--gp-noise-floor-db 1` | Minimum observation noise before calibrated noise is combined |
| `--lambda-l1 0.2` | Sparse nonnegative attenuation prior strength, scaled by cell area |
| `--lambda-tv 0.5` | Contiguity/total-variation strength, scaled by cell length |
| `--tv-epsilon 0.05` | Smooth-TV numerical epsilon |
| `--max-iterations 600` | Projected-gradient limit for each MAP fit |
| `--tolerance 1e-5` | Relative iterate or objective-change convergence rule |
| `--bootstrap-samples 20` | Deterministic parametric refits used for exceedance frequency |
| `--attenuation-threshold-db-per-m 2` | Cell attenuation-density exceedance threshold |
| `--evidence-threshold 0.7` | Minimum bootstrap frequency for component/evidence activation |
| `--minimum-component-cells 2` | Smallest four-connected reported component |
| `--receiver-clearance-cm 0` | Optional radius around sampled poses; at least half a cell is marked as limited free evidence |
| `--seed 0` | Bootstrap random seed |
| `--min-links 4` | Independent transmitter-receiver geometries through a cell |
| `--min-transmitters 2` | Distinct APs through a cell |
| `--min-angle-bins 2` | Occupied ray-direction bins |
| `--angle-bins 12` | Equal bins over unoriented angles `[0,180)` degrees |
| `--max-receiver-distance-cm 100` | Maximum cell distance to sampled support |
| `--min-sensitivity 0.5` | Minimum weighted local ray-length sensitivity |
| `--min-conditioning 0.1` | Minimum local directional Fisher eigenvalue ratio |
| `--min-pass-consistency 0.5` | Minimum weighted `1/(1 + between/within SD)` |
| `--min-repeated-links 3` | Independent supported links having at least two passes |
| `--allow-shared-calibration` | Explicitly reuse the sole calibration; intended for known-identical synthetic sources, not ordinary real APs |
| `--overwrite` | Replace existing derived outputs |
| `--show` | Open the figure after saving |

If display cells are materially finer than the physical spacing or kernel
length, the terminal/report warns. Hatched field cells are outside the sampled
convex hull or calibration-distance range. Leave-one-location-out RMSE/MAE is
reported when at least four unique receiver locations are available.

### Model and evidence semantics

The field model uses the calibrated log-distance mean plus an isotropic
squared-exponential Gaussian-process residual. Repeated-sample and between-pass
variance produce heteroscedastic observation noise. Cholesky solves with
adaptive jitter are used; covariance matrices are never explicitly inverted.
Posterior standard deviation is conditional on fixed calibration, kernel, and
pose parameters—it does not yet propagate calibration-parameter or pose
uncertainty.

For calibrated links, the 2D forward model is

`excess_i = sum_j(link_length_ij * attenuation_density_j) + noise_i`.

Exact link/cell intersection lengths have metre units. A deterministic
projected-gradient MAP optimizer with backtracking imposes nonnegativity,
area-scaled L1 sparsity, and length-scaled smoothed anisotropic total variation.
The report stores its objective history, residuals, convergence, and fits at
0.5x/1x/2x joint regularization. No threshold is hidden.

The displayed 0-1 obstacle value is a parametric-bootstrap frequency that a MAP
cell exceeds the configured dB/m threshold. It is a **relative attenuation
evidence score, not a calibrated occupancy posterior probability**. State codes
in the NPZ are: 0 unknown (score 0.5), 1 sampled/AP cell with limited free
evidence, 2 observable attenuation evidence, and 3 conflicting free/attenuation
evidence. Conflicts remain visible. Neither state 0 nor state 1 authorizes
flight.

The supplied calibration's hash/version and any declared hardware, channel,
height, or orientation fields must match the survey sidecar. Independent links
are deduplicated by AP and geometry. A shape can be emitted
only where link count, AP count, angular diversity, receiver distance,
sensitivity, conditioning, pass repeatability, metadata, calibration, full ray
coverage, and every MAP/bootstrap convergence check pass. Reported components
are labeled **potential attenuation-causing obstacles**, never confirmed
objects. Metrics include supporting links/APs, cell count, area, perimeter,
axis-aligned width/height, PCA major/minor dimensions and angle, centroid,
mean/minimum evidence, a one-cell discretization bound, and whether the region
touches unresolved space. There is no morphological closing.

Known `REPLACE_WITH_...` template values count as unresolved metadata and block
shape claims even when matching placeholders appear in both files.

### Inference outputs

`OUTPUT_DIR` contains:

1. `inference.png`: measured RSSI points, estimated RF posterior mean,
   conditional posterior standard deviation, data/link support, dB/m excess
   attenuation, and bootstrap obstacle/attenuation evidence. Points and APs are
   shown; the selected field AP is cyan and labeled `(field)`. Lines are known
   AP-to-receiver links, not a reconstructed trajectory.
2. `inference_arrays.npz`: `x_m`, `y_m`, posterior mean/std, field density,
   sample/receiver distance and extrapolation, attenuation, bootstrap frequency,
   evidence score and state, observability mask, independent/repeated link,
   AP/angle counts, sensitivity, conditioning, pass consistency, and component
   labels.
3. `inference_report.json`: input/calibration paths and SHA-256 hashes, all
   settings and seed, Python/NumPy/Matplotlib/platform versions, calibration
   contents, per-link robust/pass statistics, outlier counts, GP diagnostics,
   optimizer objective/residual/convergence, regularization sensitivity,
   observability failures, component metrics, warnings, supported conclusions,
   and the safety statement.

Outputs with the same input bytes, parameters, platform/dependency versions,
and fixed seed are deterministic. Determinism does not mean the room is known
with certainty.

## Deterministic synthetic validation

Run a recoverable crossing-link rectangle, a no-obstacle false-positive check,
and the deliberately underdetermined single-AP case:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py simulate --scene one-rectangle --geometry crossing --seed 0 --output .\synthetic_output\rectangle
.\.venv\Scripts\python.exe rf_mapper.py simulate --scene empty --geometry crossing --seed 0 --output .\synthetic_output\empty
.\.venv\Scripts\python.exe rf_mapper.py simulate --scene one-rectangle --geometry single-ap --seed 0 --output .\synthetic_output\single_ap
```

POSIX:

```sh
python rf_mapper.py simulate --scene one-rectangle --geometry crossing --seed 0 --output synthetic_output/rectangle
python rf_mapper.py simulate --scene empty --geometry crossing --seed 0 --output synthetic_output/empty
python rf_mapper.py simulate --scene one-rectangle --geometry single-ap --seed 0 --output synthetic_output/single_ap
```

`simulate` options are `--scene` (`empty` or `one-rectangle`), `--geometry`
(`crossing` or `single-ap`), `--seed` (default 0), `--output` (default
`synthetic_output`), `--grid-resolution-cm` (25), `--receiver-spacing-cm` (50),
`--bootstrap-samples` (8), `--max-iterations` (1000), and `--overwrite`.

Each directory contains `survey_samples.csv`, `survey_metadata.json`,
`calibration_samples.csv`, `calibration.json`, `ground_truth.npz`, and
`validation.json`. The report provides attenuation RMSE, IoU, precision,
recall, false-positive rate, predicted occupied fraction, symmetric mean
boundary distance, Hausdorff distance, bounding-box
dimension errors, optimizer diagnostics, and support failures. Default crossing
geometry should report `potential_attenuation_components`; the empty case
should report `no_supported_component`; single AP must report
`insufficient_observability` and no dimensions. Synthetic success is a code
validation, not evidence of real-room accuracy.

To exercise the complete inference writer on the synthetic crossing data:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py infer .\synthetic_output\rectangle\survey_samples.csv --metadata .\synthetic_output\rectangle\survey_metadata.json --calibration .\synthetic_output\rectangle\calibration.json --allow-shared-calibration --grid-resolution-cm 25 --kernel-length-scale-cm 50 --lambda-l1 0.08 --lambda-tv 0.12 --max-iterations 2000 --tolerance 0.00005 --bootstrap-samples 8 --evidence-threshold 0.625 --minimum-component-cells 2 --max-receiver-distance-cm 100 --min-links 4 --min-transmitters 2 --min-angle-bins 2 --min-sensitivity 0.5 --min-conditioning 0.1 --min-pass-consistency 0.5 --min-repeated-links 3 --seed 0 --output-dir .\synthetic_output\rectangle_inference
```

The shared-calibration flag is defensible only here because the generator gives
all synthetic APs identical transmit/propagation parameters.

## Tests and checked-data smoke commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q rf_mapper.py rf_mapping tests
```

The test suite checks exact legacy grouping/statistics, malformed serial/data
rows, missing/contradictory metadata, per-pass robust statistics and outliers,
calibration recovery and pass confounding, GP shape/uncertainty/duplicates,
horizontal/vertical/diagonal/boundary/zero-length ray intersections, MAP
nonnegativity/convergence, unknown/free/evidence/conflict semantics,
observability rejection/acceptance, component dimensions, deterministic files,
empty-scene false evidence, crossing-link rectangle recovery, single-AP
suppression, full inference outputs, and legacy plotting.

The Windows checked-data smoke test is the three-command copy/plot/infer block
under **Start here**. It should warn that metadata is unavailable, warn that 5
cm display pixels are finer than 50 cm measurement spacing, and refuse an
obstacle claim. Those warnings are successful scientific behavior.

## Stronger real experiment protocol

1. Identify the exact ESP32 board/chip and antenna; photograph markings and the
   antenna side.
2. Rotate the exposed credential and create only the ignored local header.
3. Run the empty-space calibration sweep at several known 3D distances with
   fixed height and yaw/pitch/roll.
4. If repeatability supports it, mark and physically measure a controlled room
   grid at 10-20 cm spacing. Reducing only plot pixels is not data collection.
5. Collect at least three passes. Alternate traversal direction (the CLI does
   this) and, in separate trials, randomize or counterbalance point order so
   monotonic environmental/time drift is distinguishable from position.
6. Record AP xyz, receiver z/orientation, pose uncertainty, exact board/antenna,
   channel/bandwidth/PHY, trial time, people/doors/furniture state, and a
   measured ground-truth floor sketch.
7. Collect an empty-room baseline, then add one object of known footprint,
   height, and material. Cardboard/wood, water-filled objects, and metal behave
   differently; never treat “wall loss” as universal.
8. Prefer at least two separately calibrated, spatially separated AP/transmitter
   positions. Reconnect/reconfigure and collect one v2 CSV per AP in the same
   coordinate frame so rays cross.
9. Keep people out, or label deliberately dynamic-person trials separately.
10. Hold out trials and compare evidence with ground truth using IoU,
    precision/recall, boundary error, bounding dimensions, and evidence
    calibration/reliability curves—not pictures alone.

For two real APs, do not use shared calibration. Assuming files `ap_a.csv`,
`ap_b.csv` and matched sidecars/artifacts:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py infer .\survey_output\ap_a.csv .\survey_output\ap_b.csv --metadata .\survey_output\ap_a_metadata.json --metadata .\survey_output\ap_b_metadata.json --calibration .\calibration\ap-a.json --calibration .\calibration\ap-b.json --field-ap-id ap-a --grid-resolution-cm 10 --seed 0 --output-dir .\inference_output\two_ap_trial
```

Do not manufacture a shape if the report still says
`insufficient_observability`; add genuinely different link angles/AP positions,
passes, calibration quality, and ground truth.

## Common failures and recovery

| Message/symptom | Recovery |
| --- | --- |
| `PermissionError(13)` / access denied on COM | Close Serial Monitor/Plotter and every serial process; find the COM owner, reconnect, and confirm the current port |
| `No serial ports were found` | Use a data cable/driver, reconnect, inspect Device Manager, or pass the confirmed `--port` |
| `The ESP32 did not become ready` | Check the ignored local header, rotated password, 2.4 GHz compatibility, fixed AP availability, board reset, and correct baud |
| `ERROR,SET_HOTSPOT_CREDENTIALS` | Replace both placeholders locally and upload again |
| `ERROR,WIFI_CONNECT_TIMEOUT` | Verify local values without printing them; keep the hotspot awake and compatible with 2.4 GHz |
| Width/height not exact spacing multiples | Change physical extent or spacing; the coordinate convention is not silently changed |
| Metadata hash/schema/count mismatch | Pair the sidecar with its original unedited CSV, or regenerate a truthful sidecar—never alter the hash to conceal edits |
| Calibration non-positive `n` or singular | Check metres versus centimetres, use at least three well-separated distances, and verify RSSI weakens with range |
| Calibration did not converge | Inspect outliers/orientation/time drift; then increase iterations only if diagnostics justify it |
| Missing calibration/AP geometry | Supply v2 rows, matching metadata/AP xyz, and calibration whose `ap_id` matches each link |
| Output already exists | Choose a new directory/path or explicitly add `--overwrite` for derived outputs |
| `insufficient_observability` | This is not a software failure; collect crossing multi-AP links and repeated consistent passes |
| Optimizer/bootstrap not converged | Increase the iteration budget or revise grid/regularization/noise after inspecting the report; components stay suppressed |
| Analysis-grid or dense-ray limit | Increase `--grid-resolution-cm` or analyze a smaller bounded trial; the prototype refuses allocations that are likely to exhaust memory |

## Drone integration and CSI boundary

Future collection should ingest time-aligned VIO pose and covariance rather than
manual x/y. Pose uncertainty must enter link noise or a fuller probabilistic
model. Optical loop closures/relocalization should correct historical RF sample
poses before rebuilding the RF layer. Multi-agent records need stable device/AP
IDs, synchronized clocks, a validated shared-frame transform, and merge only
after that transform is established. The dock remains the origin/coordinator
and heavier-compute point.

CSI is intentionally not implemented. Read [the CSI follow-on design](docs/CSI_FOLLOW_ON.md)
after supplying the exact board marking/photo and toolchain. One PCB antenna and
10 Hz scalar RSSI cannot implement RIM, SAR, through-wall imaging, or centimetre
obstacle mapping.

## Scientific context

- [WiFi Imaging (Farrell, McAuley, and Doyle, 2021)](https://ceur-ws.org/Vol-3097/paper32.pdf)
  motivates a forward attenuation model and spatial regularization, but its real
  experiment used 20 calibrated RF sources—not one hotspot and nine points.
- [Structure from WiFi](https://arxiv.org/abs/2403.02235) and its
  [inverse k-visibility extension](https://arxiv.org/abs/2408.07757) motivate
  distance correction, known router/receiver trajectories, crossing geometry,
  and conservative observability. Their controlled trials used hundreds to
  thousands of measurements and document multipath/dynamic-person limitations.
- [EGO-Planner-v2](https://github.com/ZJU-FAST-Lab/EGO-Planner-v2) supports the
  need for robust onboard geometric perception/planning; it does not validate
  scalar RSSI as collision sensing.
- [SfM on-the-fly project](https://yifeiyu225.github.io/on-the-flySfMv2.github.io/)
  is the conceptual multi-agent optical backbone for pose/submap fusion, not an
  RSSI obstacle algorithm.
- The [drone SAR IEEE record](https://ieeexplore.ieee.org/document/7304729/)
  used dedicated UWB radar hardware and antennas; Wi-Fi was the control link.
- [RF-based Inertial Measurement](https://dl.acm.org/doi/10.1145/3341302.3342081)
  used high-rate complex CSI and multi-antenna arrays and assumed a floor plan in
  its particle-filter example.

These references constrain the claims here; their accuracy or resolution is not
transferred to this hardware.
