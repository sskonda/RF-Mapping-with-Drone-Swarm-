# ESP32 Code

All code executing directly on an ESP32 belongs here.

The implemented [RSSI sketch](RF_Capture/RSSI/esp32_rssi_mapper/) connects to a
2.4 GHz hotspot and answers PING and MEASURE commands at 115200 baud. Keep the
sketch directory named esp32_rssi_mapper so Arduino recognizes its matching
esp32_rssi_mapper.ino file. The local wifi_credentials.h must remain beside it.

Use USB for the first flash, Wi-Fi ArduinoOTA for subsequent development uploads,
and USB/serial for recovery. The existing serial acquisition protocol and Python
interfaces are unchanged; OTA does not transport RSSI measurements over Wi-Fi.
See the [survey workflow](../Docs/Design/RF_Mapping/prototype_workflow.md) for mapping
and [CSI research](../Docs/Research/RF_Mapping/CSI_FOLLOW_ON.md) for future capture work.

Future flight-controller code belongs in Autonomy/Flight_Controller; navigation
interfaces, RF capture, communications, sensor drivers, and shared utilities
should receive directories when implemented.

## Board and partition requirements

The exact physical ESP32 board/module, chip revision, flash capacity, USB versus
USB-to-UART wiring, and BOOT/RESET wiring remain unconfirmed. The schematic's
ESP32-S3 references do not establish which board is running this sketch. Confirm
those details before choosing an upload target or recovery pin sequence.

Use **esp32 by Espressif Systems** in Arduino IDE 2.x Boards Manager. ArduinoOTA
ships with that core; install no third-party OTA library. Keep the uploader and
firmware on the same core version. The generic API/build check used core **3.3.12**,
**ESP32 Dev Module**, **Flash Size: 4MB (32Mb)**, and **Partition Scheme: Default
4MB with spiffs (1.2MB APP/1.5MB SPIFFS)** (`esp32:esp32:esp32:PartitionScheme=default`).
These are validation settings, not a board recommendation or hardware validation.

For the real board, select a supported partition scheme with `data,ota` and two
`app` slots, `ota_0` and `ota_1`. Do not select **No OTA**, **Huge APP**, or a
single-app scheme. Inspect the selected core's `tools/partitions/<scheme>.csv`
(or the build's generated `partitions.csv`); menu labels alone are insufficient.
The checked core's `default.csv` contains:

| Partition | Type/subtype | Offset | Size |
| --- | --- | --- | --- |
| otadata | data/ota | 0xe000 | 0x2000 (8,192 bytes) |
| app0 | app/ota_0 | 0x10000 | 0x140000 (1,310,720 bytes) |
| app1 | app/ota_1 | 0x150000 | 0x140000 (1,310,720 bytes) |

The complete table ends at 4 MiB. Each compiled application `.bin` must fit in
**both** app slots, and the whole table must fit the actual flash. Check the
actual binary file size as well as the IDE's compile size report. Initial USB
flashing installs the bootloader and partition table. The ArduinoOTA workflow
here uploads only the application; changing partitions requires a new USB flash.
See Espressif's [partition guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/partition_table.html)
and [OTA layout requirements](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/ota.html).

## First flash: USB

1. Rotate the previously exposed hotspot password. Commit `5e9b538` contains
   historical hotspot credentials; removal from HEAD did not remove Git history.
   The audit found no copies of those values in current tracked files. Do not
   reproduce them. History rewriting requires separate explicit approval.
2. Beside `esp32_rssi_mapper.ino`, copy `wifi_credentials.example.h` to
   `wifi_credentials.h` **only if the local file does not already exist**. In a
   local editor, replace the hotspot placeholders and add/replace
   `#define OTA_PASSWORD "REPLACE_WITH_YOUR_OTA_PASSWORD"` with a unique, strong
   development password, different from the Wi-Fi password. Keep the OTA setting
   as a macro so a missing definition can be detected. Real values belong only
   in this ignored header. Do not put credentials in commands, logs, screenshots,
   datasets, or commits. Compiled firmware also contains credentials; keep build
   artifacts private and outside Git. The sketch's IDE export `build/` directory
   and local `.bin`/`.elf` files are ignored because they can embed credentials.
3. From the repository root, confirm the ignore rule:

   ```sh
   git check-ignore ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h
   git ls-files -- ESP32_Code/RF_Capture/RSSI/esp32_rssi_mapper/wifi_credentials.h
   ```

   The first command prints the path; the second must print nothing. A missing,
   empty, or unchanged OTA password disables OTA and prints
   `STATUS,OTA_DISABLED,SET_OTA_PASSWORD` once at boot. Wi-Fi/serial measurement
   remains available with valid hotspot credentials. A missing local header is
   a compile error; copy the template. Hotspot placeholders retain the existing
   `ERROR,SET_HOTSPOT_CREDENTIALS` behavior.
4. Open `RF_Capture/RSSI/esp32_rssi_mapper/esp32_rssi_mapper.ino` in Arduino IDE.
   Install/select the Espressif board entry matching the confirmed hardware under
   **Tools > Board**, its correct flash size, and the verified OTA partition
   scheme. Leave upload speed at the board's supported default. Set **Core Debug
   Level: None** and leave verbose upload output off to avoid sensitive logs.
5. Power the stationary development board with a data-capable USB connection.
   Under **Tools > Port**, select its serial device (the COM port that appears in
   Windows Device Manager, or the corresponding Linux/macOS serial device).
   Close Python acquisition and other serial monitors. Click **Upload**. If
   needed, use the identified board's documented bootloader-entry procedure.
6. Open **Tools > Serial Monitor**, select **115200 baud** and **Newline**, and
   reset the board. With valid credentials, expect this sequence (channel/RSSI
   vary):

   ```text
   STATUS,FIRMWARE,1.1.0
   STATUS,CONNECTING
   STATUS,CONNECTED,6,-50
   READY
   STATUS,OTA_ENABLED,rf-mapper-esp32,3232
   ```

   `OTA_ENABLED` means initialization was requested; discovery/upload still
   needs verification because `ArduinoOTA.begin()` has no success return value.
   Send `PING`: expect exactly `READY`. Send `MEASURE,0,0`: expect
   `START,0,0,50`, 50 existing `DATA` records at 100 ms intervals, then
   `DONE,0,0,50` and `READY`. No SSID, BSSID, or password is printed by this sketch.

## Normal upload: Wi-Fi ArduinoOTA

1. Keep the board powered and connect the computer to the same reachable LAN as
   its hotspot connection. Stop Python acquisition and wait for `DONE`/`READY`.
   Upload only while stationary, with no flight or measurement in progress.
2. Keep the same board/core/flash/partition settings. Increase `FIRMWARE_VERSION`
   in the sketch for each distinct firmware, for example from `1.1.0` to `1.1.1`.
   Verify/compile and check that the new application fits both OTA slots.
3. Open **Tools > Port**. mDNS advertises the Arduino service (`_arduino._tcp`);
   the network entry normally appears as `rf-mapper-esp32 at <device-IP>` under
   network ports (wording varies by IDE/OS). Select that entry, retaining the
   confirmed ESP32 board selection. USB can remain connected for power and
   serial observation; selecting the network port determines the upload path.
4. Click **Upload** and enter the OTA password in the IDE prompt. Use the password
   currently installed on the device. If changing it in the new header, this
   upload uses the old password; the new password applies after reboot. Leave
   verbose upload logging off; the core's uploader arguments contain the password.
5. Wait for the IDE's successful upload result and the automatic restart.
   `STATUS,OTA_START` and `STATUS,OTA_END` are emitted over serial during transfer.
   Re-select the USB/service serial port, open Serial Monitor at 115200, and reset
   if the boot output was missed. Confirm the **new** `STATUS,FIRMWARE,<version>`,
   `READY`, and a successful `PING`/measurement. Record that the upload used the
   network port. Port reappearance or `OTA_END` alone does not prove the new
   application booted. ArduinoOTA provides no network Serial Monitor here.

Only the normal idle branch calls `ArduinoOTA.handle()`. Serial commands take
priority, and `measurePoint()` is unchanged: 50 RSSI samples, 100 ms spacing,
115200 baud, and the same START/DATA/DONE/READY records. No OTA handler, flash
write, or update callback runs inside a measurement. An upload attempted during
a measurement may wait or time out; retry after stopping acquisition. A transfer
blocks normal commands until it finishes/fails. On observed Wi-Fi loss, the
service is stopped; the original reconnection path runs, and OTA starts again
on a connected idle iteration. No background OTA task is added.

### Discovery, direct IP, and errors

- If the network port is absent, verify startup/version/OTA status over serial,
  valid local credentials, the same LAN, and absence of AP/client isolation or
  VPN routing conflicts. Refresh **Tools > Port** or restart the IDE. Check the
  OS mDNS service (Bonjour/Avahi as applicable). Give each simultaneously powered
  mapper a unique stable `OTA_HOSTNAME`, such as a configured unit suffix.
- mDNS discovery uses UDP 5353. The device's OTA invitation port is UDP **3232**;
  firmware data uses a TCP connection **from the ESP32 to the uploader**. Permit
  the IDE/Python on the trusted private LAN. Direct IP bypasses mDNS only, not
  isolation or a blocked TCP return connection. Do not forward OTA to the Internet.
- Obtain the device IP privately from the router/hotspot DHCP lease list or
  local name resolution of `rf-mapper-esp32.local`. For a direct-IP upload, use
  **Sketch > Export Compiled Binary** with the confirmed board/partition settings.
  Select `esp32_rssi_mapper.ino.bin`, **not** a merged, bootloader, partition, or
  filesystem binary. Keep the exported files out of Git.
- Use the official `tools/espota.py` from the installed core, not a separately
  downloaded uploader. The core directory is typically under
  `%LOCALAPPDATA%/Arduino15/packages/esp32/hardware/esp32/<version>` on Windows,
  `~/.arduino15/packages/esp32/hardware/esp32/<version>` on Linux, or
  `~/Library/Arduino15/packages/esp32/hardware/esp32/<version>` on macOS.
  With Python 3 in a real terminal, run `python` (or `py -3` on Windows), then:

  ```python
  import getpass, runpy
  uploader = input("Full path to the installed tools/espota.py: ")
  device = input("Device IPv4 address: ")
  firmware = input("Full path to esp32_rssi_mapper.ino.bin: ")
  ota = runpy.run_path(uploader)
  result = ota["main"](["-i", device, "-p", "3232", "-P", "3233",
                        "-f", firmware, "-a", getpass.getpass("OTA password: "), "-r"])
  print("Uploader exit code:", result)
  ```

  This prompts without echoing the password or putting it in shell history or
  process arguments. Do not add `-d`/`--debug`: that uploader logs its options.
  Allow inbound TCP **3233** on the computer for this explicit fallback port.
  Exit code 0 still requires the boot-version/serial verification above.
- `ERROR,OTA,<code>` uses Espressif's `ota_error_t`: 0 authentication, 1 begin,
  2 connection, 3 receive, 4 end. Check password/core pairing for authentication
  errors, partition capacity for begin errors, TCP reachability for connection
  or receive errors, and binary integrity/power for end errors. An interrupted
  transfer is not proof of a successful update. Retry only after checking the
  running version; recover by USB if OTA no longer responds.

## USB/serial recovery

1. Stop acquisition, close Serial Monitor, and connect a data cable or the
   controlled internal service fixture. Identify the actual serial device.
2. Correct the local credentials or firmware, restore a known working version,
   and select the confirmed board, flash size, and OTA-capable partition scheme.
   Select the **serial** port under **Tools > Port**, then **Upload**.
3. If the broken application prevents automatic reset or USB enumeration, use
   the board/chip's documented ROM download/BOOT/RESET sequence and supported
   USB or UART interface. Exact pins and timing cannot be specified until the
   hardware and wiring are confirmed. Do not guess a chip variant or burn eFuses.
4. Use the board's normal full serial flash recipe to reinstall bootloader,
   partition table, OTA selection data, and application, not an app-only upload.
   A full flash erase is not normally needed; it destroys stored settings.
   Check boot version,
   `PING`, one complete measurement, then rediscovery and a Wi-Fi test upload.

USB flashing remains available in this development firmware even with broken
Wi-Fi credentials or a non-running application, provided the physical ROM
download interface is accessible and unrestricted. This change configures no
Secure Boot, Flash Encryption, ROM download restriction, or JTAG eFuses.

## Production security and physical design

ArduinoOTA password authentication is a **development convenience** on a trusted
LAN. This implementation does not provide HTTPS transport, require signed images,
enforce anti-rollback, or implement a boot self-test/automatic rollback policy.
A firmware version string is an operator check, not a security counter.

Before production, confirm the SoC/module, silicon revision, flash capacity,
partition layout, boot/service wiring, and existing security provisioning. Then:

1. Migrate to ESP-IDF **HTTPS OTA** with certificate/hostname verification and
   **signed firmware**, with protected signing keys and a release/signing process.
2. Size **dual A/B OTA app partitions plus otadata** for the complete signed image
   and its padding. Add boot self-tests for essential device functions and mark
   a new image valid only after they pass; enable rollback for crashes, failed
   self-tests, and interrupted updates. Test power loss and recovery on hardware.
3. Enforce release versions and a chip-supported **anti-rollback security version**
   policy. Coordinate security-version advancement with self-test acceptance and
   the recovery image; a revoked image must not become the fallback.
4. Provision the variant's supported **Secure Boot** and production **Flash
   Encryption**, with protected device keys/credential storage. Signed Secure
   Boot enforces authorized firmware execution; hiding USB alone is not security.
5. Restrict or disable **ROM download and JTAG**, including native USB debug or
   download interfaces where present, after validating a compatible controlled
   service/recovery process. Locking these interfaces can remove today's USB
   recovery path; the final design must account for that deliberately.
6. Remove the externally accessible USB programming connector from the final
   drone. Retain internal **pogo/service pads** for the supported power, ground,
   reset/boot, and data signals, accessible only with an authorized fixture.
   Require authorized signed recovery images and control fixture/key access.

No target-specific security commands or irreversible eFuse changes belong in
this prototype update. Follow the final chip's documentation rather than assuming
that ESP32, S3, and C3 security/recovery facilities are interchangeable.

Official references reviewed for this implementation:
[ArduinoOTA example](https://github.com/espressif/arduino-esp32/blob/3.3.12/libraries/ArduinoOTA/examples/BasicOTA/BasicOTA.ino),
[ArduinoOTA implementation](https://github.com/espressif/arduino-esp32/blob/3.3.12/libraries/ArduinoOTA/src/ArduinoOTA.cpp),
[official uploader](https://github.com/espressif/arduino-esp32/blob/3.3.12/tools/espota.py),
[ESP-IDF OTA example](https://github.com/espressif/esp-idf/tree/master/examples/system/ota/native_ota_example),
[HTTPS OTA](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/esp_https_ota.html),
[security overview](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/security/security.html),
[Secure Boot](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/security/secure-boot-v2.html),
and [Flash Encryption](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/security/flash-encryption.html).
ESP32-specific pages describe principles here; use the target selector once the
hardware is known. See the [validation record](../Development/Reports/esp32_ota_verification.md)
for actual checks and untested hardware behavior.
