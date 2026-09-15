# CSI follow-on experiment (not implemented)

Do not add board-specific CSI firmware until the exact ESP32 board marking,
chip, antenna implementation, and build framework are confirmed. A clear board
photo is useful. The present Arduino sketch records 10 Hz scalar RSSI from one
PCB antenna; it is not CSI, a phased array, SAR, or RF-based inertial
measurement.

## Proposed controlled milestone

1. Confirm that the exact chip and ESP-IDF release support CSI receive mode.
   Prefer a small ESP-IDF test project based on Espressif's documented CSI APIs
   over altering the stable Arduino survey first. Arduino may remain the simple
   RSSI path; whether its installed core exposes the necessary APIs is a
   board/toolchain-specific fact to verify.
2. Use a fixed, controlled packet source and log its stable privacy-preserving
   ID, channel, bandwidth, PHY configuration, packet sequence, and intended
   packet rate. Measure achieved rate and packet loss instead of assuming it.
3. In the Wi-Fi receive callback, copy only the timestamp, metadata, and CSI
   payload into a bounded queue. A worker task should serialize and transport
   records. Lengthy parsing, file I/O, or network I/O must not run in the
   callback.
4. Store one record per packet: host/device time, sequence, AP ID, receiver pose
   and covariance, RSSI, noise floor when available, channel/PHY metadata, CSI
   length, and raw per-subcarrier complex values. Version the schema and record
   dropped callback/queue records.
5. Budget transport from the actual CSI payload length and packet rate. Plain
   115200-baud serial may be insufficient; compare buffered binary serial,
   higher validated baud rates, SD storage, and network transfer without
   allowing logging traffic to contaminate the sensing experiment unnoticed.
6. Fix antenna height and yaw/pitch/roll. Repeat rotations deliberately to
   measure PCB-trace directivity; do not treat that directional response as an
   obstacle.
7. Treat commodity phase as uncalibrated until packet timing, carrier-frequency
   offset, sampling-frequency offset, phase wrapping, automatic gain, and
   hardware-dependent subcarrier artifacts are characterized. Preserve raw data
   and every sanitization parameter.
8. First validate repeatability in empty space, then with one known material and
   geometry. Use held-out trials and report errors/calibration curves before any
   drone integration.

The likely ESP-IDF entry points are `esp_wifi_set_csi_rx_cb`,
`esp_wifi_set_csi_config`, and `esp_wifi_set_csi`, but their availability and
configuration must be checked against the confirmed chip and installed ESP-IDF
version. See the [official ESP-IDF CSI documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/wifi-driver/wifi-vendor-features.html)
and [Espressif's ESP-CSI examples](https://github.com/espressif/esp-csi).

One PCB antenna still lacks the simultaneous multi-antenna geometry used by
RIM, and scalar or single-antenna CSI does not justify promises of through-wall
imaging or centimetre obstacle outlines. Camera/IMU/VIO/SfM remains the pose and
collision-geometry backbone.
