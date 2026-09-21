# Flight controller: stage 1 bench firmware

**This image cannot stabilize or fly the quadrotor. Remove every propeller.**
It brings up the BNO055, MTF-02P and four motor outputs so their timing, identity
and electrical behavior can be measured before a rate controller is written.
The default build cannot arm. No hardware was connected during development.
Software validation is recorded in
[the verification report](../../../Development/Reports/flight_bench_verification.md).

## Design and ownership

Core 1, priority 24, owns initialization and the complete 10 ms acquisition →
validity/safety → bench command → MCPWM path. There is no estimator or flight
controller yet. Core 0 owns the serial console and 1 Hz reporting. Later RF,
Wi-Fi and swarm work belongs on core 0; the existing Arduino RSSI/OTA sketch is
a separate image, not a task to insert into this loop.

Two fixed mailbox records carry an 8-byte command and a telemetry snapshot.
One ESP-IDF spinlock protects their bounded copies; neither core calls drivers,
prints or waits while holding it. An occupied command slot requests a stop.
A separate task notification preserves stop requests even when a command is
pending; stopping clears that slot. There is no retrying seqlock or command queue.

The flight task uses fixed-size records and bounded UART reads. I2C uses the
hardware synchronous driver, with a 2 ms timeout per transaction and a 1.5 ms
clock-stretch limit. IDF v5.5.5 also has a **50 ms bus-clear recovery timeout**
(`s_i2c_master_clear_bus`), so 2 ms is not a bound on complete call duration.
These settings are bench limits, not measured BNO055 timing guarantees. Drivers
allocate at initialization only. No application allocation, printing, filesystem,
network or update work occurs in the acquisition/output loop. The minimal IDF
build includes only the required components. There is no OTA service or OTA partition.

A core-1 GPTimer interrupt forces every PWM generator low when a 30 ms output
lease expires. Updating/releasing outputs and the timeout ISR share a short
critical section so a timeout cannot interleave with output release. The next
task write detects the expired lease and disarms. The task watchdog additionally
panics after one second without progress. The lease is a motor-off backstop, not
permission to miss deadlines. Interrupt masking, a failed MCU or a shorted MOSFET
still requires an independent physical motor-power disconnect.

| File | Exact responsibility; why it stays separate |
| --- | --- |
| `CMakeLists.txt` | IDF project, ESP32-S3 target and minimal dependency selection. |
| `sdkconfig.defaults` | CPU, scheduler, logging, watchdog, flash and interrupt configuration. |
| `.gitignore` | Local generated build/configuration exclusions. |
| `main/CMakeLists.txt` | IDF component sources, dependencies, warnings and stack-usage artifacts; different scope from the project file. |
| `main/config.h` | Sole definition of provisional pins, baud rate and bench operating limits. |
| `main/sensors.h` | Fixed sensor/parser records and the acquisition/decoder contracts. |
| `main/sensors.c` | BNO055 configuration/I2C and bounded MTF UART acquisition, isolated from portable parsing. |
| `main/sensor_decode.c` | Byte order, scaling, quaternion normalization, Micolink validation and source-clock progression; host tests need no mocked IDF. |
| `main/bench.h`, `main/bench.c` | Explicit DISARMED/ARMED state, freshness, finite-value checks, motion limits and one-pulse lifetime. This can be tested without motors. |
| `main/motors.h`, `main/motors.c` | Four active-high MCPWM outputs and the independent lease. PWM handles never leave this module. |
| `main/motor_stop.lf` | Places the force-low driver function in IRAM. IDF's MCPWM control IRAM option does **not** place this function there. The linker fragment cannot be expressed as C. |
| `main/main.c` | Task/mailbox ownership, scheduling, deadline monitoring, console and telemetry. No additional command framework is needed. |
| `README.md` | Operating contract, hardware gates and validation sequence. |

`main/` is IDF's application-component boundary. The parent `Autonomy/` follows
the repository's established ownership. No utility directory or future control
module is created. `Development/Tests/Flight_Controller/` owns its CMake runner
and two independent test programs (sensor protocol and bench safety), rather than
mixing hardware tests with the RF Python package. The verification report holds
measured build/test evidence separately from these operating instructions.

## What the sensor data means

BNO055 runs in IMUPLUS mode: quaternion and gyro, without a motor-disturbed
magnetometer heading reference. Bosch specifies 100 Hz fusion output; polling at
100 Hz does not establish a 100 Hz feedback stream. Firmware revision **0x0314
or newer** must assert fusion data-ready in `INT_STA` before a sample is counted.
Older revisions still show raw diagnostics but remain invalid for arming.
Calibration requires accelerometer and gyro level 3, the relevant self-tests,
fusion-running status, and the configured mode/units. Burst reads preserve
multi-byte register consistency. Gyro is rad/s; quaternion order is w,x,y,z.
After a data read, any intervening data-ready flag is cleared conservatively:
it could describe the sample just read. This can discard an update; it prevents
counting that flag again as evidence for another sample. Measure the resulting
accepted rate, including its dependence on polling phase.

The IMU timestamp is the host's **observation** of data-ready, not the instant
of physical sampling. Under on-time polling, up to a polling interval plus
transport delay separates the observation from register availability; internal
fusion latency remains unmeasured. Counters only advance on witnessed valid
updates. Equal numerical samples are legitimate and are not used as a freshness
test. No acceleration integration or absolute XYZ claim is made.
Expired validity is latched off until another valid measurement arrives, so a
32-bit microsecond clock wrap cannot revive old sensor data.

Configure MTF-02P to **Micolink**, not AUTO/MAVLink/MSP, with MicoAssistant before
connecting it. Manufacturer documentation specifies 50 Hz, 115200 baud, 8N1,
3.3 V UART signaling and a 5 V supply. The decoder accepts the documented
27-byte range/flow message, verifies identifiers, length and checksum, and
requires an advancing sequence and source millisecond counter. It quarantines
the first frame, discontinuities and the first packet after more than 60 ms
without a checksum-valid packet. Header noise cannot refresh that timebase.
Duplicate/corrupt frames do not renew sample freshness. Partial frames expire
after 20 ms; accepted samples retain the first byte's host observation time.
Expiry runs even on empty polls, so clock wrap cannot revive an old fragment.
These are host observation ages, not synchronized physical sampling times.
UART errors/backlogs invalidate data and are drained in bounded chunks.

`flow_cm_s_at_1m` is the manufacturer's height-normalized flow field. Multiplying
by height gives a scale estimate, **not yet a validated body/world velocity**.
Mounting, axis signs, rotational flow, sensor offset from the centre of rotation
and latency need characterization. Range is line-of-sight distance to the surface,
not absolute altitude. The bench accepts 0.08–2 m and raw quality ≥100; these are
conservative application settings, not validated flight thresholds.

## Hardware facts still unverified

The user specifies ESP32-S3-WROOM-1-N4, BNO055 over I2C, brushed 8520 motors and
MTF-02P. The repository names BNO055/MTF-02P and contains ESP32-S3 and generic
NMOS schematic symbols, but supplies no assembled-board evidence or validated
netlist/pin map. The ICM-42688-P library/model is not evidence of an installed IMU.

Verify module marking/flash capacity, reset/boot/console wiring, BNO address and
firmware, I2C pull-ups and clock stretching, sensor mounting, MTF firmware/protocol,
power integrity, motor supply voltage, driver part/rating/polarity, gate pull-downs,
flyback paths, battery/current limits, motor identity/rotation and propeller type.
Mass, inertia, thrust curve, hover duty and vibration/latency are unknown. The
repository's 40 mA flow-module note differs from the current manufacturer's
100 mA average-current specification; budget from the exact unit and measurement.

The output driver contract is **active high, low = off**, with external pull-downs
and a physical motor-power cut. Software cannot hold pins low during power-on,
ROM boot, reset or loss of power. First scope the outputs with motor power
disconnected. Never connect an unverified active-low stage to this firmware.
All temporary assignments occur once in `main/config.h`; GPIO numbers refer to
the ESP32, not connector or module-pad numbers. No CW/CCW assignment is assumed.

Strong position hold remains an unproven later capability: BNO bandwidth/latency
may limit a small quad's rate loop; flow needs texture, light, adequate height,
rotation compensation and trustworthy range. Integrated flow drifts without
external position corrections. Range over changing/sloping terrain is not a
fixed world Z. Motor authority, power margin and heading stability are unmeasured.

## Build, flash and host tests

Validated toolchain: ESP-IDF **v5.5.5**, ESP32-S3, 240 MHz, 4 MB flash, no PSRAM.
Install outside this repository (Linux prerequisites include git, cmake, ninja,
Python venv support and the usual IDF build dependencies):

```sh
git clone --branch v5.5.5 --depth 1 --recursive https://github.com/espressif/esp-idf.git "$HOME/esp-idf-v5.5.5"
"$HOME/esp-idf-v5.5.5/install.sh" esp32s3
. "$HOME/esp-idf-v5.5.5/export.sh"

# From the repository root; this default build cannot arm.
idf.py -C ESP32_Code/Autonomy/Flight_Controller build
idf.py -C ESP32_Code/Autonomy/Flight_Controller size size-components
cmake -S Development/Tests/Flight_Controller -B /tmp/fc-tests -DFC_SANITIZE=ON
cmake --build /tmp/fc-tests
ctest --test-dir /tmp/fc-tests --output-on-failure
```

After the electrical checks, remove props and disconnect motor power while
flashing. The default console is IDF UART0; USB-to-UART versus native USB wiring
is unverified. For native USB Serial/JTAG, select that console in `idf.py
menuconfig` before rebuilding. Set the actual port instead of copying the example:

```sh
FC_PORT=/dev/ttyUSB0
idf.py -C ESP32_Code/Autonomy/Flight_Controller -p "$FC_PORT" flash monitor
```

Only after verifying active-high/off behavior, external pull-downs, sensor
operation, motor labels, and a current-limited supply, build the motor-test image:

```sh
idf.py -C ESP32_Code/Autonomy/Flight_Controller -B ESP32_Code/Autonomy/Flight_Controller/build-bench -D CMAKE_C_FLAGS=-DFC_BENCH_ENABLE=1 build
idf.py -C ESP32_Code/Autonomy/Flight_Controller -B ESP32_Code/Autonomy/Flight_Controller/build-bench -p "$FC_PORT" flash monitor
```

Enablement permits bench arming; it does not arm at boot. Put the airframe flat
and immobile above a textured, illuminated surface. Send `a`, wait for ARMED,
then send **one** of `1` (FL), `2` (FR), `3` (RR), `4` (RL). Use separate commands;
pasting `a1` may overflow the mailbox and stop. The selected output gets 10% duty
at 20 kHz for nominally 150 ms, then disarms. If it does not spin, do not infer a
failed channel or increase power blindly: check voltage, current and starting
torque. Each pulse requires a new arm. No command extends or switches a pulse.

`d`, `!`, or any unrecognized non-newline character requests an immediate forced
low, without a ramp. Flight-task notification interrupts its scheduled wait;
during I2C, the request is applied when acquisition returns. Bus recovery can
exceed the 6 ms task budget; the 30 ms output lease is the independent backstop.
Measure both paths. The software-stop acceptance gate below is unproven, including
under injected bus faults; a failure blocks progression to rate control. Console
reception itself can be delayed by serial reporting; a physical power cut is the
hard e-stop. Disconnecting the console cannot leave a motor running indefinitely: pulse, arming and output-lease timeouts still apply.

The relative quaternion rotation limit is 15° from the armed pose (including
yaw); this avoids inventing a sensor/body mounting transform. It is **not an
absolute flight tilt limit**. The bench angular-rate norm limit is 1 rad/s.
Flow/range and IMU must remain valid/fresh throughout a pulse. Any invalid state,
late command, missed budget or expired output lease disarms. There are no
integrators to reset in this stage.

## Measurable stage-1 acceptance gates

All hardware rows below are **pending**. Save scope captures and a ten-minute
telemetry log with board/sensor revisions, power source and build commit.

| Check | Pass criterion |
| --- | --- |
| Host regression | Both C tests pass under ASan/UBSan; late fragments, long reception gaps and header noise cannot renew freshness. All existing RF tests pass. |
| Target build | Default and bench-enabled v5.5.5 images link without application warnings; inspect map for the lease ISR and force-low routine in IRAM. |
| Power-on/reset/disarm | Every gate stays at the measured off level through boot, reset, sensor init failure and disarm. No unintended pulse on any channel. |
| Individual channels | Each command energizes only its physical labelled motor; other three gates stay low. Record physical position and observed CW/CCW viewed from above, independently of pin labels. |
| PWM | 20 kHz ±1%; 10% duty ±1 percentage point; no pulse exceeds 170 ms under normal scheduling. Stop never waits for a PWM period or ramps down. |
| Software stop | Once the core-0 receiver publishes stop, all gates low within 6 ms. End-to-end serial stop ≤100 ms including telemetry; verify both with trace/scope. |
| Lease backstop | Stall/suspend the flight task during a pulse without disabling interrupts: all gates low within 31 ms of the last renewal; explicit re-arm required afterwards. Use a temporary debugger/test build, props removed; JTAG can disable system watchdogs. |
| Sensor rate/age | Over ten minutes, IMU witnessed valid updates average 90–100/s and MTF advancing frames 48–52/s, with no sensor-age limit violations. Failure means investigate polling phase, firmware, transport or rate; do not fabricate a faster rate. |
| IMU checks | Unit quaternion after decoding; stationary gyro norm <0.05 rad/s after calibration. Hand rotation has the expected signed axis response and integrated angle within 10% for measured 90° motions. Record the mounting transform for the next stage. |
| Range/flow | Flat targets at 0.2, 0.5, 1.0 m: range error ≤0.03 m. Translate on both axes and rotate in place; log signs, scale, delay, quality and rotational contamination. Velocity accuracy is not certified by this stage. |
| Invalid/stale inputs | Disconnect each sensor, corrupt serial packets, stop source timestamps, and interrupt I2C: output drops on invalidity, or by the configured 30/60 ms age limit plus ≤16 ms acquisition/scheduling allowance; no automatic re-arm. |
| Timing/stack | Maximum task execution ≤6000 µs, maximum absolute period deviation ≤2000 µs, zero deadline misses over ten minutes, flight-stack free high-water mark ≥1024 bytes. These are gates, not claimed measurements. |

Telemetry reports cumulative mean/worst execution, worst absolute deviation from
the 10 ms period, deadline misses, stack free high-water mark in **bytes**, data
validity, host observation ages, source counter and accepted/rejected frames.
The execution interval includes sensing, output, watchdog feeding and snapshot
publication; wait/early stop handling is outside it. Snapshot reporting is one
cycle behind accounting. It is task duration, not physical sensor-to-actuator
latency. Measure the latter with I2C/UART/PWM capture and known motion. A validity
flag describes the last received measurement; arming additionally checks age.

Fault numbers: 0 OK, 1 explicit stop, 2 build locked, 3 sensor, 4 command,
5 timeout, 6 motion, 7 deadline, 8 output/watchdog. State 0 is DISARMED, 1 ARMED;
motor -1 means all off. No sensor timestamp is valid merely because its age prints
a small value: check validity and accepted sample counters too.

## Subsequent stages, gated in order

1. **Complete this bench stage.** Record the hardware results above; do not fit
   props until electrical off behavior and all four motor identities are proven.
2. **Mixer verification, props off.** Use body FRD and a local frame whose x points
   along initial heading, y right and z down. Record actual motor torque signs;
   test isolated roll/pitch/yaw requests, collective bounds, desaturation and
   nonfinite inputs. Prioritize roll/pitch, shed yaw/collective where necessary,
   and feed achieved-versus-requested torque back to anti-windup. Do not copy
   ESP-Drone's per-motor clipping as a desaturation strategy.
3. **Rate control on a restrained single-axis rig.** Sample-driven PID with
   filtered derivative on measured rate, integral bounds and saturation-aware
   anti-windup. Test anti-windup and derivative behavior on the host, then tune
   the innermost loop with measured latency and step response. Stop if BNO055
   bandwidth/latency is inadequate; a different IMU is then a hardware decision.
4. **Quaternion attitude on a restrained/tethered rig.** Verified mounting maps
   gyro to body FRD and quaternion to body→local, tested with identity/90°/180°,
   q/−q and inverse rotations. Quaternion error P control supplies limited body
   rates. Establish absolute tilt/rate limits and a safe manual recovery path.
5. **Altitude.** Measure thrust versus duty/battery voltage and hover feedforward;
   characterize range tilt correction and vertical velocity. Tune velocity then
   Z-position loops; a tethered lift is not proof of free hover stability.
6. **XY velocity.** Calibrate flow scaling, signs, rotational compensation and
   time alignment. Use ToF for scale and gyro for derotation. Test commanded
   velocities with speed/acceleration/tilt/thrust limits in a controlled enclosure.
7. **Local XYZ position.** Integrate validated horizontal velocity with explicit
   drift/validity handling; Z is range-derived over a known surface. Measure hold
   error against an independent reference over a declared duration and surface.
8. **Trajectory limiting.** Bound position-derived velocity, vertical speed,
   acceleration, tilt and thrust. Test setpoint steps and mode transitions.
9. **Flight failsafes.** Expand this stage's motor-off safety to mode-appropriate
   sensor/link/battery loss behavior; test on a rig before free flight. Never
   carry stale integrators or setpoints through invalidity/disarm/re-arm.
10. **Timing under load.** Re-measure WCET, period, jitter, sensor age, stack and
    actuator latency with RF/Wi-Fi load on core 0 before each flight release.

The planned cascade is position P → bounded velocity → velocity PID → bounded
acceleration/thrust with calibrated hover feedforward → quaternion attitude P →
bounded body-rate PID → desaturating X mixer. Outer loops consume new range/flow
observations; faster prediction is labelled prediction, never new feedback.

The future estimator boundary will expose body→local quaternion, body rates,
local velocity/position, per-source timestamps and per-axis validity. External
VIO/XYZ corrections enter as timestamped local-frame position observations with
uncertainty and reset identification, rather than modifying controller state.
Frame/time alignment and correction gating belong to the estimator. No unused
VIO callback, covariance storage or generic estimator framework is added now.

## Research basis

See the [verification report](../../../Development/Reports/flight_bench_verification.md)
for repository/history inspection and the exact upstream revisions reviewed.
Primary hardware references are the [Bosch BNO055 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bno055-ds000.pdf),
[ESP32-S3-WROOM-1 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf),
[MTF-02/02P manual](https://micoair.cn/zh/docs/sensors/sensors/mtf-02-02p-sensors)
and [Micolink definition](https://micoair.cn/zh/docs/sensors/micolink).
IDF contracts were checked against the installed v5.5.5 sources and official
[I2C](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/peripherals/i2c.html),
[MCPWM](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/peripherals/mcpwm.html),
[GPTimer](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/peripherals/gptimer.html),
[FreeRTOS](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/system/freertos_idf.html)
and [watchdog](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32s3/api-reference/system/wdts.html)
documentation. Published sensor specifications and upstream results are not
measurements of this airframe.
