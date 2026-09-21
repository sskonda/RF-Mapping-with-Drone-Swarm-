# ESP32-S3 flight bench verification

Software validation on 2026-09-20, starting from `87ecdad` on `main`.
No board, sensors, motor drivers or motors were connected. This is the first
sensor/motor bring-up stage; it cannot stabilize or fly an aircraft. Default
builds cannot arm. The [operator guide](../../ESP32_Code/Autonomy/Flight_Controller/README.md)
contains exact build/flash/test commands, every module's responsibility, unknown
hardware facts, measurable hardware acceptance gates and the ordered flight plan.

## Repository inspection and design decision

Inspected the complete original 222-file tracked inventory and all 11 reachable
commits, root/subsystem architecture and contributing documents, CI, Python
package/test structure, RF firmware and its serial/OTA behavior, FPGA RTL, hardware
inventory, and readable Altium component/parameter strings. Hardware accounts for
161 files, including binary CAD libraries, models and history. This was not an
electrical connectivity, PCB layout or DRC validation. No assembled-board evidence,
flight-control implementation, flight tests or applicable `AGENTS.md` existed.

History separates RF mapping (`5e9b538`, `2918e70`), repository/package cleanup
(`345ac23`, `f94bfe9`, `2b7de29`), schematics (`79489e1`), development OTA (`75c9938`)
and FPGA RTL (`de3952c`). None establishes a working flight platform. The existing
Arduino RSSI/OTA image is unsuitable as the deterministic control-loop owner.
It remains separate; this IDF image contains no OTA service or OTA partition.

One core-1 task owns acquisition, validation, bench state and motor commands.
Core 0 owns command reception and telemetry. A timer ISR only forces motors off;
it is not another control stage. The two bounded mailbox records and separate
stop notification are smaller than a queue-based control pipeline.

Hardware prevents a defensible strong-position-hold claim today: BNO055 supplies
orientation/rate, not absolute XYZ; flow integration drifts and needs validated
height, mounting, derotation and timing; range follows terrain. BNO055 fusion
latency, motor authority, thrust/hover calibration and heading stability are
unmeasured. The future estimator contract is documented, without unused VIO or
controller code. Mixer, PID, frame-transform and position-control implementation
and their tests are gated after the physical bring-up results.

The two existing-file changes (CI and the ESP32 README) were shown as a diff
before applying them. All implementation and test files are new.

## Primary sources and implementation history

Bosch's [BNO055 datasheet revision 1.8](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bno055-ds000.pdf)
establishes IMUPLUS's nominal 100 Hz fusion output, quaternion and gyro scaling,
clock stretching, boot/mode delays and read-cleared interrupt status. Its data-ready
support starts at software 03.14. Earlier firmware is diagnostic-only here;
re-reading unchanged registers cannot establish new feedback. Polling phase and
the conservative post-read acknowledgement can reduce the accepted rate.

The [ESP32-S3-WROOM-1 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
was checked against the assumed N4 target. IDF's I2C, UART, MCPWM, GPTimer,
FreeRTOS and watchdog contracts were checked in official documentation and
**v5.5.5**, commit `b774170ff46c393eeb5e495ea37936038d3f4f4f`, source. In particular,
`mcpwm_generator_set_force_level()` is not covered by the MCPWM control-IRAM
option; the small linker fragment explicitly places that motor-off dependency
in instruction RAM. Synchronous I2C allocates during initialization, not per poll.
Timeout recovery still needs measurement; a timeout argument is not a WCET proof.

Mico's [MTF-02/02P manual](https://micoair.cn/zh/docs/sensors/sensors/mtf-02-02p-sensors)
and [Micolink definition](https://micoair.cn/zh/docs/sensors/micolink) supply the
27-byte frame, additive checksum, source clock/sequence, status fields and flow
units of cm/s at 1 m. They specify 50 Hz and 115200 baud. The test packet is
synthetic, not a capture from this unit. Manufacturer supply/current data and the
repository's hardware note disagree; the installed hardware must settle that.

Reviewed ESP-Drone default-branch revision
[`db0f6562e4f67cccee3acac4dff39c9aaea4e5fa`](https://github.com/espressif/esp-drone/tree/db0f6562e4f67cccee3acac4dff39c9aaea4e5fa),
including `stabilizer.c`, `controller_pid.c`, `position_controller_pid.c`, `pid.c`,
`power_distribution_stock.c`, `estimator_kalman.c`, `kalman_core.c`,
`flowdeck_v1v2.c`, `commander.c`, motor drivers and their relevant history:

| Upstream evidence | Lesson for this airframe |
| --- | --- |
| [Position hold addition](https://github.com/espressif/esp-drone/commit/b00325a3ad1653c5cc0573e510c7ef11851bb502) | Implemented flow/range hold for its own hardware; not evidence for MTF/BNO performance or transferable gains. |
| [Vibration filter change](https://github.com/espressif/esp-drone/commit/c57499403a3905a846a0ac4622c12d52c07d2a2c) | Lower bandwidth addressed vibration but the author explicitly identified instability/agility costs. Measure delay before choosing filters. |
| [I2C watchdog fix](https://github.com/espressif/esp-drone/commit/5847bc01b81650d0546fb4d066244266fad58ded) | Two 400 kHz buses caused watchdog trouble; the patch lowered one bus to 100 kHz. Bus speed alone does not prove determinism. |
| [S3 timer stack increase](https://github.com/espressif/esp-drone/commit/6b5677ecaefe4dfb3f20a5f7c15ed608eb66ecde) | 3072 to 4096 bytes; retain stack margin until actual high-water measurement. |
| [IMU initialization fix](https://github.com/espressif/esp-drone/commit/527ee2e09cb446d414926562260de31403fb943e) | Startup sequencing/failure handling remained material in 2025. Failed initialization must prohibit arming. |
| [Kalman default change](https://github.com/espressif/esp-drone/commit/494bb4f484ce5299baedfd3417da7b67a60d8a65) | Estimator choice is coupled to sensing and measured behavior, not a reason to import its task/queue structure. |

ESP-Drone's sensor-ready stabilizer and multirate cascade are useful precedents.
Its historical Euler attitude controller, separate estimator synchronization,
derivative-on-error PID and independent motor clipping are not adopted. Flow hold
uses height, attitude and gyro-dependent rotational compensation, not direct XY
position. Commander timeout handling and motor shutdown were traced separately
from the controller. An additional safety commit on an experimental branch was
not treated as default-branch behavior. No upstream source code was copied.

Compared current PX4 at
[`2fc441493eb887199c279e2eff990f3f4cd0deef`](https://github.com/PX4/PX4-Autopilot/tree/2fc441493eb887199c279e2eff990f3f4cd0deef)
with its [multicopter controller documentation](https://docs.px4.io/main/en/flight_stack/controller_diagrams).
Reviewed position/velocity control, quaternion attitude, rate control and sequential
desaturation. The useful design is bounded position P → velocity PID →
acceleration/thrust with hover feedforward → quaternion attitude → body-rate PID,
with measured-rate derivative filtering and allocator saturation feedback.
Its estimator, messaging and allocation framework would be unjustified here.

Relevant PX4 history includes [stale acceleration setpoints filling the velocity
integrator](https://github.com/PX4/PX4-Autopilot/commit/7c318a3296aa2413a6e8feeb4b08f723f1e80907),
[rejecting zero hover thrust](https://github.com/PX4/PX4-Autopilot/commit/bc042d6918fdf5ae5ef9a08b08b575dcfa0ef7ea),
and [filtered quaternion setpoint-derivative feedforward](https://github.com/PX4/PX4-Autopilot/commit/2a0e0481713ca44802d74e9d3ba4a92f384d138f).
These support explicit freshness/reset rules and validated thrust normalization.
The newer attitude reference model is additional complexity with no demonstrated
benefit on this BNO055 platform. Published upstream behavior is not our test data.

## Resulting tree

```text
ESP32_Code/Autonomy/Flight_Controller/
  .gitignore
  CMakeLists.txt
  sdkconfig.defaults
  README.md
  main/
    CMakeLists.txt
    config.h
    sensors.h
    sensors.c
    sensor_decode.c
    bench.h
    bench.c
    motors.h
    motors.c
    motor_stop.lf
    main.c
Development/Tests/Flight_Controller/
  CMakeLists.txt
  test_sensors.c
  test_bench.c
Development/Reports/flight_bench_verification.md
```

The operator guide explains each firmware file and directory. The test CMake file
builds portable production code without IDF mocks; `test_sensors.c` exercises wire
format/freshness, while `test_bench.c` exercises arming/pulse safety. Combining
them would mix distinct input contracts. The report belongs in the existing
reports directory; no new generic infrastructure or dependency was introduced.

## Review passes and unnecessary-code audit

1. **Correctness:** checked byte order, signed decoding, units, quaternion norm/sign,
   source-clock/sequence rollover, IMU revision/status and pulse/arm transitions.
   No unverified sensor/body transform or motor rotation was invented. Post-read
   DRDY acknowledgement conservatively avoids counting an intervening flag twice.
2. **Safety:** traced every init failure, disarm, invalid/stale command/sensor,
   repeated pulse, deadline and timer expiry to forced-low output. Added latched
   age invalidation against long-running clock wrap. NaN/Inf, bad norms and
   excessive motion cannot arm. Driver polarity and physical shutdown remain gates.
3. **Real time:** one statically allocated pinned task; no loop allocation/logging,
   filesystem or network calls. Checked IDF call paths, bounded UART/event reads,
   I2C timeouts/recovery, stop wakeup, ISR race exclusion and IRAM placement.
   Scheduling skips late catch-up iterations. Actual timing remains unmeasured.
4. **Computation:** retained one quaternion normalization per accepted read and
   squared norm/dot guards, with no Euler/trigonometric control math. Reused sensor
   records and one elapsed-time sample at each decision boundary. Minimal IDF
   component selection removed unrelated build dependencies.
5. **Memory:** replaced two one-entry static queues with fixed mailbox records,
   saving 160 application static bytes. Core-0 local stack frame fell 320→240 bytes.
   Parser storage is 29 bytes; no duplicate raw sensor history or unused estimates.
6. **Structure:** five cohesive C modules, each below 200 physical lines. Portable
   decoding and safety are separate only because they have independent host tests.
   Kept initialization error checks local instead of creating a utility framework.
7. **Line by line:** re-read all added C, headers, build/linker configuration and
   tests; removed unused includes and queue machinery. Every retained state field
   serves acquisition, safety or requested instrumentation. No TODO control stubs,
   speculative interfaces, unused controller gains or debug logging remain.
8. **Regression:** rebuilt both target variants after the final sensor fixes,
   reran sanitizer tests and the existing RF suite, and checked compiler analysis,
   map/stack artifacts and whitespace. The final pre-commit audit found no further
   material simplification within this stage that preserved its safety evidence.

Rejected optimizations: fast-math/approximate inverse square root would weaken
finite/norm checks without measured benefit; fixed point adds conversion/range
burden; unlocked snapshots/seqlock retries complicate correctness and timing;
asynchronous I2C adds state/error handling before a measured need. Shrinking the
4 KiB stack or placing the entire loop in IRAM needs hardware evidence. Removing
defensive validity checks or caching duplicate motor-output state was not justified.
No timing improvement is inferred from source size or successful compilation.

## Executed validation and measurements

Installed official IDF/tools outside the repository and built with ESP-IDF v5.5.5,
Xtensa GCC 14.2.0 and Ninja. Host tests used GCC 13.3, C11, optimization, strict
warnings, assertions, ASan and UBSan. RF tests used an isolated Python 3.12
environment; unrelated globally installed ROS pytest plugins were excluded.

| Check | Result |
| --- | --- |
| Default ESP32-S3 image | Passed; `FC_BENCH_ENABLE=0`. |
| Motor-test image | Passed; compiler response file verified `-DFC_BENCH_ENABLE=1`. |
| CTest | 2/2 executables passed under ASan/UBSan. |
| Sensor coverage | Quaternion/scaling/status, source reset/duplicate/wrap, packet corruption at every byte, truncation recovery, 200,000 deterministic noise bytes. |
| Bench coverage | All four logical channels, default lockout, arm/pulse expiry, repeated command rejection, explicit stop, motion, invalid/stale inputs, command age and time rollover. |
| GCC static analyzer | Portable decoder and bench state code passed `-fanalyzer`. |
| Existing RF pytest | 72 passed; two existing metadata-unavailable warnings. |
| Existing RF unittest / wheel / compileall | 72 passed / wheel built / passed. |
| GitHub Actions | Added host and IDF-container jobs; local equivalents passed. Remote CI has not been run. |

No motor-driver or I2C/UART hardware test is implied by portable unit tests.
Mixer-sign/desaturation, PID anti-windup and body/local-frame tests do not yet
exist because their corresponding control stages have not been implemented.

| Source file | Physical lines | Nonblank code lines, excluding comments |
| --- | ---: | ---: |
| `main/bench.c` | 72 | 69 |
| `main/main.c` | 181 | 174 |
| `main/motors.c` | 107 | 102 |
| `main/sensor_decode.c` | 95 | 89 |
| `main/sensors.c` | 127 | 116 |
| Firmware C total | **582** | **550** |
| `main/bench.h` | 19 | 16 |
| `main/config.h` | 48 | 43 |
| `main/motors.h` | 6 | 4 |
| `main/sensors.h` | 39 | 32 |
| `test_bench.c` | 128 | 122 |
| `test_sensors.c` | 131 | 123 |

| Metric | Evidence/result |
| --- | --- |
| Application binary | 191,600 bytes, both variants; 1 MiB application slot. |
| Application-attributed static data | 4,650 bytes (`libmain.a`: BSS 4,634 + data 16), including the 4,096-byte flight stack. |
| Whole-image static data | 17,352 bytes (BSS 6,600 + data 10,752); excludes RAM-resident code and driver/runtime heap. |
| Mailbox | 136 bytes plus an 8-byte spinlock; bounded copies, no queue allocation. |
| Compiler local stack frames | Flight task 224, console 240, sensor poll 160, motor write 80, lease callback 32 bytes. These exclude callees/interrupts and are not runtime high-water measurements. |
| Motor-off code placement | ELF symbols: lease callback `0x40376874`, GPTimer ISR `0x40377990`, MCPWM force-level `0x40377f9c`, in instruction RAM. |
| Flight execution mean/worst, jitter, missed deadlines | Not measurable without hardware; firmware reports them. |
| Runtime stack high-water / initialization heap | Not measured; stack high-water reporting is implemented. |
| Sensor age/rate/latency and physical motor order/polarity | Not measured; must pass the operator guide's bench gates. |

The software stage is ready for props-off bench validation. Passing builds/tests
does not validate electrical behavior, watchdog shutdown latency, stable flight
or position hold. Progress to the mixer and innermost controller only after the
recorded physical gates pass.
