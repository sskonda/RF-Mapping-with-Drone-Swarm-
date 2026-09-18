# ESP32 development OTA verification

Validated on 2026-09-18 against baseline `79489e1` on `main`. The initially
checked-out branch was one commit behind and was fast-forwarded before editing.

## Repository and upstream review

Before implementation, inspected the complete tracked-file inventory (216 files),
all eight reachable/reflog commits, firmware changes across history, Python module
and test structure, serial consumers, operator documentation, and hardware target
references. The byte-level audit covered 250 unique Git blobs and the 99 ZIP
members in the current hardware tree. CAD inspection established file scope and
target references, not electrical validation of the schematics or board.

Historical hotspot credentials remain in commit `5e9b538`. Their values were not
printed. Searches for those values, including UTF-16 representations and expanded
ZIP members, found no copies in the current tracked contents. Reviewed credential
assignments and common private-key/token patterns without printing values. Only
the placeholder credential template is tracked; `wifi_credentials.h` remains
ignored. This is a scoped source/history audit, not proof that arbitrary binary
assets cannot contain other sensitive information. Rotate the exposed hotspot
password. History was not rewritten.

Compared Espressif's current ArduinoOTA BasicOTA example and implementation,
including the installed **3.3.12** release, with ESP-IDF's native OTA example,
partition/rollback documentation, and security guides linked in the
[ESP32 operator guide](../../ESP32_Code/README.md). ArduinoOTA owns its mDNS/UDP
dependencies, so the sketch adds only `ArduinoOTA.h`. Its transfer and callbacks
run from `handle()`; the sketch calls that only in the connected idle branch.
`begin()` returns void, so the enabled status is not a claim that binding or
discovery succeeded. `end()` stops the UDP/mDNS service on observed disconnection.

## Builds and partition capacity

No existing Arduino CLI/core was found in the searched system/user locations.
Installed an isolated official toolchain under `/tmp/rf-ota-validation`, without
changing repository dependencies or the user's Arduino configuration:

- Arduino CLI **1.5.2-rc.1**, commit `fef6e48df` (the official latest download).
- Espressif Arduino core **3.3.12** from Espressif's official package index.
- Generic FQBN **esp32:esp32:esp32:PartitionScheme=default**, 4 MiB flash.

This is an API/build check only. The actual board/chip is unresolved. Builds used
a copy of the sketch and randomly generated, disposable credentials outside the
repository; no ESP32 or hotspot connection/upload was attempted.

Commands executed (temporary paths reflect this validation session):

```sh
/tmp/rf-ota-validation/arduino-cli --config-file /tmp/rf-ota-validation/arduino-cli.yaml core install esp32:esp32@3.3.12
/tmp/rf-ota-validation/arduino-cli --config-file /tmp/rf-ota-validation/arduino-cli.yaml compile --fqbn esp32:esp32:esp32:PartitionScheme=default --warnings all --jobs 4 --build-path /tmp/rf-ota-validation/build /tmp/rf-ota-validation/sketch/esp32_rssi_mapper
python /tmp/rf-ota-validation/arduino-data/packages/esp32/hardware/esp32/3.3.12/tools/gen_esp32part.py /tmp/rf-ota-validation/valid-partitions.bin /tmp/rf-ota-validation/decoded-partitions.csv
```

The compile command passed for four headers: configured OTA password, missing
OTA definition (legacy header), empty password, and template placeholder.
No compiler warnings were emitted. The configured build reported **970,059 bytes
of program storage**, **51,592 bytes of static RAM**. Its application binary was
**970,208 bytes**; these sizes depend on core/settings/credential lengths.

Decoded the actual generated partition binary using Espressif's tool and compared
it with the build's CSV: `otadata` is 8,192 bytes; `ota_0` and `ota_1` are each
1,310,720 bytes. The configured application fits each slot with **340,512 bytes
spare**. The full table ends at **4,194,304 bytes**. This validates the generic
build's layout, not the unknown device's installed flash/table.

## Protocol, lifecycle, and host checks

Compared every existing firmware function against the baseline. The seven
credential/Wi-Fi/serial/measurement functions are byte-for-byte unchanged:
`credentialsConfigured`, `printConnectionStatus`, `connectToHotspot`,
`readCommandLine`, `parseMeasurementCommand`, `measurePoint`, and `handleCommand`.
All existing serial, command, reconnect, and sample constants are unchanged.
No Python implementation, tests, mapping calculation, or dataset was modified.

A temporary C++ host harness compiled the actual sketch with mock Serial, Wi-Fi,
clock, and ArduinoOTA interfaces using `g++ -std=c++17 -Wall -Wextra -Werror`:

```sh
python /tmp/rf-ota-validation/host_check.py
```

Passed all four OTA credential configurations. Checks covered STA/sleep/automatic
reconnect setup, 115200 baud, boot-version output, PING, malformed/out-of-range/
overflow/partial/CRLF commands, exact START/DATA/DONE/READY output, 50 samples with
100 ms simulated spacing, uint32 clock wrap, disconnect during measurement,
connection timeout, service stop/restart, and OTA error callbacks. A pending
mock OTA request remained unserviced throughout each measurement and was serviced
on the following idle loop. This checks sketch control flow; it does not emulate
radio timing, actual OTA authentication, flash writes, or the ESP32 scheduler.
The harness and its disposable headers were not added as project infrastructure.

The existing Python suite passed **72 tests**:

```sh
/tmp/rf-ota-validation/python-env/bin/python -m unittest discover -s Development/Tests/RF_Mapping -v
```

The temporary environment used the existing dependencies and an editable install
of `Mapping/RF_Mapping`. Checked the documented direct-IP arguments through the
installed `espota.py` argument parser: UDP target 3232, TCP host 3233, application
upload, debug disabled. No network transfer was attempted.

Inspected the installed generic board's USB/serial `esptool_py` and network
`esp_ota` recipes. The normal serial recipe still writes bootloader, partition
table, `boot_app0.bin` (OTA selection data), and application. This confirms that
adding ArduinoOTA leaves the development USB upload path configured; it is not a
physical USB recovery test.

## Final review and hardware limits

Reviewed the complete change diff line by line. `git diff --check` passed.
Verified the credential header and sketch build/binary export ignore rules,
placeholder-only tracked credential content, and absence of the historical
credential values in the updated tracked files. Build outputs remain outside Git.

Not hardware-tested: first USB flash, real password rejection, mDNS discovery,
Wi-Fi or direct-IP transfer, reboot/version change after upload, radio sample
timing, reconnection under RF loss, power interruption, or ROM download recovery.
The operator guide specifies how to perform these checks. Exact board/module and
chip revision, flash capacity, USB/UART/BOOT/RESET wiring, and current security
provisioning are required before choosing target-specific settings or sequences.
No eFuses were burned and no target-specific security provisioning commands were
added. Production HTTPS/signing, A/B self-test/rollback, anti-rollback, Secure
Boot, Flash Encryption, download/JTAG restrictions, and internal service-pad
design remain future work.
