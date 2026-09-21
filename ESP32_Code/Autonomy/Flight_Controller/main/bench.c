#include "bench.h"
#include "config.h"
#include <math.h>

void bench_stop(Bench *bench, BenchFault fault)
{
    bench->state = DISARMED;
    bench->motor = -1;
    bench->fault = fault;
}

static bool healthy(const Sensors *s, uint32_t now_us)
{
    if (!s->imu.valid || !s->flow.range_valid || !s->flow.flow_valid ||
        now_us - s->imu.observed_us > FC_IMU_MAX_AGE_US ||
        now_us - s->flow.observed_us > FC_FLOW_MAX_AGE_US ||
        !isfinite(s->flow.range_m) || s->flow.range_m < FC_RANGE_MIN_M ||
        s->flow.range_m > FC_RANGE_MAX_M) return false;
    float norm2 = 0.0f;
    for (unsigned i = 0; i < 4; ++i) {
        if (!isfinite(s->imu.q[i])) return false;
        norm2 += s->imu.q[i] * s->imu.q[i];
    }
    for (unsigned i = 0; i < 3; ++i) if (!isfinite(s->imu.gyro[i])) return false;
    return norm2 > 0.99f && norm2 < 1.01f;
}

void bench_step(Bench *bench, const Sensors *s, const BenchCommand *cmd,
                uint32_t now_us, bool enabled)
{
    if (cmd->key == 'd' || cmd->key == '!') {
        bench_stop(bench, BENCH_STOP);
        return;
    }
    if (!enabled || !healthy(s, now_us)) {
        bench_stop(bench, enabled ? BENCH_SENSOR : BENCH_LOCKED);
        return;
    }
    float rate2 = 0.0f;
    for (unsigned i = 0; i < 3; ++i) rate2 += s->imu.gyro[i] * s->imu.gyro[i];
    if (rate2 > FC_BENCH_RATE_MAX_RAD_S * FC_BENCH_RATE_MAX_RAD_S) {
        bench_stop(bench, BENCH_MOTION);
        return;
    }
    if (cmd->key && now_us - cmd->issued_us > FC_COMMAND_MAX_AGE_US) {
        bench_stop(bench, BENCH_COMMAND);
        return;
    }
    if (bench->state == DISARMED) {
        if (cmd->key == 'a') {
            for (unsigned i = 0; i < 4; ++i) bench->reference_q[i] = s->imu.q[i];
            bench->armed_us = now_us;
            bench->motor = -1;
            bench->state = ARMED;
            bench->fault = BENCH_OK;
        }
        return;
    }
    float dot = 0.0f;
    for (unsigned i = 0; i < 4; ++i) dot += bench->reference_q[i] * s->imu.q[i];
    if (!(dot * dot >= FC_BENCH_ROTATION_COS2)) {
        bench_stop(bench, BENCH_MOTION);
    } else if (now_us - bench->armed_us >= FC_ARM_TIMEOUT_US ||
               (bench->motor >= 0 && now_us - bench->pulse_us >= FC_PULSE_US)) {
        bench_stop(bench, BENCH_TIMEOUT);
    } else if (cmd->key >= '1' && cmd->key < '1' + FC_MOTOR_COUNT && bench->motor < 0) {
        bench->motor = cmd->key - '1';
        bench->pulse_us = now_us;
    } else if (cmd->key) {
        bench_stop(bench, BENCH_COMMAND); /* No pulse extension or channel switching. */
    }
}
