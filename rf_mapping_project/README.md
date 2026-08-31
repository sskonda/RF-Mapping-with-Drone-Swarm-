# ESP32 RSSI 2D Mapper

This project creates a measured 2D Wi-Fi signal-strength heatmap using:

- an iPhone hotspot as the fixed 2.4 GHz transmitter;
- an ESP32 as the movable RSSI receiver;
- Arduino IDE to upload the ESP32 firmware;
- Python on the PC to guide the survey, save CSV data, and create the heatmap.

The result is an RSSI coverage map. It is not a radar image or an automatically reconstructed wall map.

## What runs where

| Program | Where it runs | Purpose |
| --- | --- | --- |
| `esp32_rssi_mapper.ino` | ESP32, uploaded with Arduino IDE | Connects to the hotspot and takes RSSI measurements |
| `rf_mapper.py` | Windows PC | Supplies coordinates, records CSV data, and draws the heatmap |

VS Code is optional. The Python program can run from PowerShell or Command Prompt. Arduino IDE alone can upload the firmware and show raw serial data, but it cannot run this Python heatmap program.

## 1. Prepare the phone

1. Open **Settings > Personal Hotspot**.
2. Enable **Allow Others to Join**.
3. Enable **Maximize Compatibility** so the hotspot uses 2.4 GHz.
4. Keep the phone plugged in, fixed in one position, and untouched during the survey.

## 2. Configure and upload the ESP32 firmware

1. Open `esp32_rssi_mapper/esp32_rssi_mapper.ino` in Arduino IDE.
2. Arduino IDE should also show `wifi_credentials.h` as another tab.
3. In `wifi_credentials.h`, leave the hotspot name or replace it with the exact name shown by the Wi-Fi scan.
4. Replace `REPLACE_WITH_YOUR_HOTSPOT_PASSWORD` with the real password. Do not share or upload the edited credential file.
5. Select **Tools > Board > ESP32 Arduino > ESP32 Dev Module**.
6. Select the ESP32 COM port under **Tools > Port**.
7. Upload the sketch.
8. Open Serial Monitor at **115200 baud**.

A successful startup resembles:

```text
STATUS,CONNECTING,Sanat's iPhone 16 Pro Max
STATUS,CONNECTED,Sanat's iPhone 16 Pro Max,aa:bb:cc:dd:ee:ff,1,-50
READY
```

If the upload stalls at `Connecting...`, hold **BOOT**, start the upload, and release BOOT when writing begins.

Close Serial Monitor after verifying `READY`. Only one program can own the COM port, so Python cannot connect while Serial Monitor is open.

## 3. Install Python

Install Python 3 from <https://www.python.org/downloads/> if the `py` command is not already available.

Open PowerShell in the `rf_mapping_project` directory and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

VS Code users can run the same commands in **Terminal > New Terminal**. No VS Code extension is required, although the Microsoft Python extension is convenient for editing.

## 4. Define the coordinate system

1. Choose one corner of the survey rectangle as `(0, 0)`.
2. Measure the rectangle in centimeters.
3. Mark a regular grid on the floor.
4. Keep the ESP32 at the same height and orientation at every point.

For a first test, use a 200 cm by 200 cm area with 50 cm spacing. That produces 25 points:

```text
(0,0), (50,0), ... (200,0)
...
(0,200), ...       (200,200)
```

Width and height must be exact multiples of the selected spacing.

## 5. Run a survey

Find the ESP32 COM port in Arduino IDE, then close Serial Monitor. For example, if the port is `COM5`, run this as one line:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py survey --port COM5 --width-cm 200 --height-cm 200 --spacing-cm 50 --passes 1 --ap-x-cm 0 --ap-y-cm 100 --show
```

Arguments:

- `--port COM5`: ESP32 serial port. Omit this argument to select from a list.
- `--width-cm 200`: survey width from `x=0` through `x=200`.
- `--height-cm 200`: survey height from `y=0` through `y=200`.
- `--spacing-cm 50`: 50 cm between measurement points.
- `--passes 1`: survey the grid once. Use three passes after the first successful test.
- `--ap-x-cm` and `--ap-y-cm`: optional phone position, shown as a star.
- `--show`: display the map after also saving it as a PNG.

At each prompt:

1. Move the ESP32 to the displayed coordinate.
2. Keep its antenna orientation unchanged.
3. Step away from the direct phone-to-ESP32 path.
4. Press Enter.
5. Wait about five seconds while 50 samples are collected.

Enter `s` to skip an inaccessible point or `q` to stop and render the partial survey.

The traversal is serpentine: one row goes left-to-right and the next goes right-to-left, reducing unnecessary walking.

## 6. Output files

The `survey_output` directory contains:

- `raw_samples_*.csv`: every measurement from the ESP32;
- `point_summary_*.csv`: sample count, median, mean, standard deviation, and IQR at each point;
- `rssi_heatmap_*.png`: the measured 2D heatmap.

The heatmap uses the median RSSI at every measured cell. It deliberately does not invent extra spatial resolution through interpolation. Less-negative RSSI values are stronger.

To rebuild a heatmap from a saved raw CSV:

```powershell
.\.venv\Scripts\python.exe rf_mapper.py plot survey_output\raw_samples_YYYYMMDD_HHMMSS.csv --ap-x-cm 0 --ap-y-cm 100 --show
```

## 7. Recommended experiment sequence

1. Run a 100 cm by 100 cm test with 50 cm spacing and one pass.
2. Confirm that the CSV and PNG files are created.
3. Run the intended area with 50 cm spacing and three passes.
4. Compare the `standard_deviation_db` and `iqr_db` columns against differences between adjacent points.
5. Only reduce the spacing if repeated surveys distinguish the closer points consistently.

## Troubleshooting

### Python reports that the COM port is unavailable

Close Arduino Serial Monitor and any other program using that COM port.

### The ESP32 never becomes ready

- Verify the hotspot password in `wifi_credentials.h`.
- Enable **Maximize Compatibility** on the iPhone.
- Keep the Personal Hotspot screen open during initial connection.
- Press the ESP32 **EN** button and try again.
- If it still times out, rename the iPhone to a simple Wi-Fi name without an
  apostrophe, such as `Sanat-iPhone`, then put that exact name in
  `HOTSPOT_SSID` and upload again.

### The ESP32 repeatedly disconnects

- Keep the phone awake and plugged in.
- Keep the ESP32 within the hotspot's reliable range.
- Use a known-good USB cable and stable USB power.

### The map changes when repeated

RSSI is sensitive to people, board orientation, furniture, doors, and multipath. Keep the experimental geometry controlled and use the median over several passes.

## Later drone integration

The manual coordinate supplied by the Python program is a temporary position source. In the drone version, replace it with the vehicle pose from visual-inertial odometry, optical mapping, UWB, or another localization system. The RSSI sample and pose still need to be timestamped and fused before plotting.
