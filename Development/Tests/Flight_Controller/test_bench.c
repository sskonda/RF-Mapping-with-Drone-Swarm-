#include "bench.h"
#include "config.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static Sensors healthy(uint32_t now)
{
    return (Sensors){
        .imu = {.q = {1, 0, 0, 0}, .observed_us = now, .valid = true},
        .flow = {.range_m = 0.5f, .observed_us = now, .range_valid = true, .flow_valid = true}
    };
}

static void step(Bench *b, const Sensors *s, char key, uint32_t now, bool enabled)
{
    const BenchCommand cmd = {.key = key, .issued_us = now};
    bench_step(b, s, &cmd, now, enabled);
}

static void test_pulses(void)
{
    const uint32_t now = 100000;
    Sensors s = healthy(now);
    Bench b = {.motor = -1};
    step(&b, &s, 'a', now, false);
    assert(b.state == DISARMED && b.motor == -1 && b.fault == BENCH_LOCKED);
    for (int motor = 0; motor < FC_MOTOR_COUNT; ++motor) {
        s = healthy(now);
        step(&b, &s, '1' + motor, now, true);
        assert(b.state == DISARMED && b.motor == -1);
        step(&b, &s, 'a', now, true);
        assert(b.state == ARMED && b.motor == -1);
        step(&b, &s, '1' + motor, now, true);
        assert(b.state == ARMED && b.motor == motor);
        s = healthy(now + FC_PULSE_US - 1);
        step(&b, &s, 0, now + FC_PULSE_US - 1, true);
        assert(b.motor == motor);
        s = healthy(now + FC_PULSE_US);
        step(&b, &s, 0, now + FC_PULSE_US, true);
        assert(b.state == DISARMED && b.motor == -1 && b.fault == BENCH_TIMEOUT);
    }
    s = healthy(now);
    step(&b, &s, 'a', now, true);
    step(&b, &s, '1', now, true);
    step(&b, &s, '1', now, true);
    assert(b.state == DISARMED && b.motor == -1); /* Repeating cannot extend a pulse. */
    step(&b, &s, 'a', now, true);
    step(&b, &s, '!', now, true);
    assert(b.state == DISARMED && b.motor == -1 && b.fault == BENCH_STOP);
    step(&b, &s, 'a', now, true);
    s = healthy(now + FC_ARM_TIMEOUT_US);
    step(&b, &s, 0, now + FC_ARM_TIMEOUT_US, true);
    assert(b.state == DISARMED);
}

static void test_invalid(void)
{
    const uint32_t now = 100000;
    for (unsigned field = 0; field < 14; ++field) {
        Sensors s = healthy(now);
        Bench b = {.motor = -1};
        step(&b, &s, 'a', now, true);
        step(&b, &s, '2', now, true);
        assert(b.motor == 1);
        if (field < 4) s.imu.q[field] = NAN;
        else if (field < 7) s.imu.gyro[field - 4] = INFINITY;
        else if (field == 7) s.flow.range_m = NAN;
        else if (field == 8) s.imu.valid = false;
        else if (field == 9) s.flow.range_valid = false;
        else if (field == 10) s.flow.flow_valid = false;
        else if (field == 11) s.imu.observed_us = now - FC_IMU_MAX_AGE_US - 1;
        else if (field == 12) s.flow.observed_us = now - FC_FLOW_MAX_AGE_US - 1;
        else s.imu.q[0] = 2.0f;
        step(&b, &s, 0, now, true);
        assert(b.state == DISARMED && b.motor == -1 && b.fault == BENCH_SENSOR);
        step(&b, &s, 'a', now, true);
        assert(b.state == DISARMED);
        s = healthy(now);
        step(&b, &s, '1', now, true);
        assert(b.state == DISARMED); /* Sensor recovery must never re-arm. */
    }
}

static void test_motion_and_time(void)
{
    uint32_t now = UINT32_MAX - 10;
    Sensors s = healthy(now);
    Bench b = {.motor = -1};
    step(&b, &s, 'a', now, true);
    s.imu.q[0] = -1.0f;
    step(&b, &s, '3', now, true);
    assert(b.motor == 2); /* Quaternion sign is immaterial. */
    now += 20;
    s = healthy(now);
    step(&b, &s, 0, now, true);
    assert(b.state == ARMED);
    s.imu.q[0] = s.imu.q[1] = sqrtf(0.5f);
    step(&b, &s, 0, now, true);
    assert(b.state == DISARMED && b.fault == BENCH_MOTION);
    s = healthy(now);
    s.imu.gyro[0] = FC_BENCH_RATE_MAX_RAD_S + 0.01f;
    step(&b, &s, 'a', now, true);
    assert(b.state == DISARMED && b.fault == BENCH_MOTION);
    s = healthy(now);
    BenchCommand cmd = {.key = 'a', .issued_us = now - FC_COMMAND_MAX_AGE_US - 1};
    bench_step(&b, &s, &cmd, now, true);
    assert(b.state == DISARMED && b.fault == BENCH_COMMAND);
    cmd.issued_us = now + 1;
    bench_step(&b, &s, &cmd, now, true);
    assert(b.state == DISARMED);
    cmd.issued_us = now - FC_COMMAND_MAX_AGE_US;
    bench_step(&b, &s, &cmd, now, true);
    assert(b.state == ARMED);
    bench_stop(&b, BENCH_DEADLINE);
    assert(b.state == DISARMED && b.motor == -1);
    printf("sizeof Sensors=%zu Bench=%zu FlowParser=%zu Command=%zu\n",
           sizeof(Sensors), sizeof(Bench), sizeof(FlowParser), sizeof(BenchCommand));
}

int main(void)
{
    test_pulses();
    test_invalid();
    test_motion_and_time();
    puts("bench safety: pulses, limits, invalid/stale inputs, stops and wrap passed");
    return 0;
}
