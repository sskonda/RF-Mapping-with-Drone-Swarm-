#pragma once

/* Provisional wiring. Verify the active-high drivers with motor power removed. */
#define FC_I2C_SDA 8
#define FC_I2C_SCL 9
#define FC_IMU_RESET 10
#define FC_MOTOR_PINS {4, 5, 6, 7} /* FL, FR, RR, RL; rotation is unassigned. */
#define FC_FLOW_RX 17
#define FC_FLOW_TX 18
#define FC_FLOW_BAUD 115200
#define FC_FLOW_UART 1
#define FC_IMU_ADDRESS 0x28
#define FC_I2C_HZ 400000
#define FC_I2C_TIMEOUT_MS 2
#define FC_I2C_STRETCH_US 1500

/* Enable only after the README's electrical and props-off checks. */
#ifndef FC_BENCH_ENABLE
#define FC_BENCH_ENABLE 0
#endif
#define FC_MOTOR_COUNT 4
#define FC_PWM_RESOLUTION_HZ 10000000
#define FC_PWM_HZ 20000
#define FC_BENCH_DUTY_PERMILLE 100
#define FC_PULSE_US 150000u
#define FC_OUTPUT_LEASE_US 30000u
#define FC_ARM_TIMEOUT_US 3000000u
#define FC_COMMAND_MAX_AGE_US 100000u
#define FC_IMU_MAX_AGE_US 30000u
#define FC_FLOW_MAX_AGE_US 60000u
#define FC_RANGE_MIN_M 0.08f /* Flow's working floor, above the ToF dead zone. */
#define FC_RANGE_MAX_M 2.0f /* Provisional bench envelope, not the sensor's rating. */
#define FC_FLOW_MIN_QUALITY 100 /* Raw units; requires surface characterization. */
#define FC_FLOW_MAX_CM_S_AT_1M 700
#define FC_BENCH_RATE_MAX_RAD_S 1.0f
#define FC_BENCH_ROTATION_COS2 0.982962913f /* cos(15 degrees / 2)^2 */
#define FC_PERIOD_US 10000u
#define FC_EXECUTION_BUDGET_US 6000u
#define FC_JITTER_LIMIT_US 2000u
#define FC_FLIGHT_CORE 1
#define FC_FLIGHT_PRIORITY 24
#define FC_FLIGHT_STACK_BYTES 4096
#define FC_REPORT_LOOPS 100u

_Static_assert(FC_BENCH_DUTY_PERMILLE > 0 && FC_BENCH_DUTY_PERMILLE <= 150,
               "Bench duty must be in (0, 15%]");
_Static_assert(FC_PERIOD_US < FC_OUTPUT_LEASE_US && FC_OUTPUT_LEASE_US < FC_PULSE_US,
               "Output lease must expire before an unattended pulse");
