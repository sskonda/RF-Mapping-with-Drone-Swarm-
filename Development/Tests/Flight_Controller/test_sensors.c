#include "sensors.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* Synthetic, little-endian Micolink frame, independently laid out from the manual. */
static uint8_t frame[MICOLINK_BYTES] = {
    0xef, 0x0f, 0x00, 0x51, 1, 20,
    100, 0, 0, 0, 0xf4, 1, 0, 0, 90, 2, 1, 0,
    0x85, 0xff, 0xc8, 1, 200, 1, 0, 0, 0
};

static void checksum(void)
{
    unsigned sum = 0;
    for (unsigned i = 0; i < sizeof(frame) - 1; ++i) sum += frame[i];
    frame[sizeof(frame) - 1] = sum & 255;
}

static void send_frame(FlowParser *p, FlowSample *s, uint32_t time, uint8_t sequence,
                       uint32_t received)
{
    frame[4] = sequence;
    for (unsigned i = 0; i < 4; ++i) frame[6 + i] = (uint8_t)(time >> (8 * i));
    checksum();
    for (unsigned i = 0; i < sizeof(frame); ++i) flow_decode(p, s, frame[i], received);
}

static void test_imu(void)
{
    const uint8_t status[BNO_STATUS_BYTES] = {0x3c, 0x0d, 1, 0, 5, 0, 2, 0, 8};
    assert(imu_status_valid(status));
    const unsigned checked[] = {0, 1, 4, 5, 6, 8};
    for (unsigned i = 0; i < sizeof(checked) / sizeof(checked[0]); ++i) {
        uint8_t bad[BNO_STATUS_BYTES];
        memcpy(bad, status, sizeof(bad));
        bad[checked[i]] ^= 1;
        if (checked[i] == 0) bad[0] = 0;
        assert(!imu_status_valid(bad));
    }
    ImuSample s = {0};
    uint8_t data[BNO_DATA_BYTES] = {0x84, 3, 0x7c, 0xfc};
    assert(!imu_decode(&s, data));
    data[13] = 0x40;
    assert(imu_decode(&s, data));
    assert(s.q[0] == 1.0f && s.q[1] == 0.0f);
    assert(fabsf(s.gyro[0] - 1.0f) < 1e-6f && fabsf(s.gyro[1] + 1.0f) < 1e-6f);
    data[13] = 0xc0; /* q and -q describe the same orientation. */
    assert(imu_decode(&s, data) && s.q[0] == -1.0f);
    data[13] = 0x7f;
    assert(!imu_decode(&s, data));
    memset(data, 0, sizeof(data));
    data[13] = data[15] = 0x2d;
    assert(imu_decode(&s, data));
    assert(fabsf(s.q[0] * s.q[0] + s.q[1] * s.q[1] - 1.0f) < 1e-6f);
    data[0] = 0; data[1] = 0x80;
    assert(imu_decode(&s, data));
    assert(fabsf(s.gyro[0] + 32768.0f / 900.0f) < 1e-6f);
}

static void test_flow(void)
{
    FlowParser p = {0};
    FlowSample s = {0};
    send_frame(&p, &s, 100, 1, 1000);
    assert(!s.range_valid && s.samples == 0);
    send_frame(&p, &s, 120, 2, 21000);
    assert(s.range_valid && s.flow_valid && s.samples == 1);
    assert(s.range_m == 0.5f && s.flow[0] == -123 && s.flow[1] == 456);
    send_frame(&p, &s, 120, 2, 22000);
    assert(!s.range_valid && s.samples == 1 && s.observed_us == 21000);
    send_frame(&p, &s, 140, 3, 41000);
    assert(s.range_valid);
    frame[22] = 0;
    send_frame(&p, &s, 160, 4, 61000);
    assert(!s.flow_valid && s.range_valid);
    frame[22] = 200; frame[16] = 0;
    send_frame(&p, &s, 180, 5, 81000);
    assert(!s.range_valid);
    frame[16] = 1; frame[10] = frame[11] = 0;
    send_frame(&p, &s, 200, 6, 101000);
    assert(!s.range_valid);
    frame[10] = 0xf4; frame[11] = 1;
    send_frame(&p, &s, 5, 0, 121000); /* Sensor reboot: one-frame quarantine. */
    assert(!s.range_valid);
    send_frame(&p, &s, 25, 1, 141000);
    assert(s.range_valid);
    frame[19] = 0x7f;
    send_frame(&p, &s, 45, 2, 161000);
    assert(s.range_valid && !s.flow_valid);
    frame[19] = 0xff;
    p = (FlowParser){0}; s = (FlowSample){0};
    send_frame(&p, &s, UINT32_MAX - 10, 255, UINT32_MAX - 10);
    send_frame(&p, &s, 9, 0, 9);
    assert(s.range_valid && s.samples == 1 && s.observed_us == 9);
}

static void test_corruption(void)
{
    for (unsigned corrupt = 0; corrupt < sizeof(frame); ++corrupt) {
        FlowParser p = {0}; FlowSample s = {0};
        send_frame(&p, &s, 100, 1, 1000);
        const uint8_t saved = frame[corrupt];
        frame[corrupt] ^= 0x80;
        for (unsigned i = 0; i < sizeof(frame); ++i) flow_decode(&p, &s, frame[i], 2000);
        assert(s.samples == 0);
        frame[corrupt] = saved;
        for (unsigned i = 0; i < 4; ++i) send_frame(&p, &s, 140 + i * 20, 3 + i, 3000 + i);
        assert(s.range_valid && s.samples > 0 && p.used == 0);
    }
    FlowParser p = {0}; FlowSample s = {0};
    for (unsigned i = 0; i < 11; ++i) flow_decode(&p, &s, frame[i], 0);
    for (unsigned i = 0; i < 4; ++i) send_frame(&p, &s, 200 + i * 20, 7 + i, 3000 + i);
    assert(s.range_valid);
    uint32_t random = 1;
    for (unsigned i = 0; i < 200000; ++i) {
        random = random * 1664525u + 1013904223u;
        flow_decode(&p, &s, random >> 24, i);
        assert(p.used < MICOLINK_BYTES);
    }
}

int main(void)
{
    test_imu();
    test_flow();
    test_corruption();
    printf("sensor decoding: units, norms, protocol, corruption, freshness and wrap passed\n");
    return 0;
}
