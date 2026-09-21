#include "sensors.h"
#include "config.h"
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
    flow_decode(p, s, frame, sizeof(frame), received);
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
        flow_decode(&p, &s, frame, sizeof(frame), 2000);
        assert(s.samples == 0);
        frame[corrupt] = saved;
        for (unsigned i = 0; i < 4; ++i) send_frame(&p, &s, 140 + i * 20, 3 + i, 3000 + i);
        assert(s.range_valid && s.samples > 0 && p.used == 0);
    }
    FlowParser p = {0}; FlowSample s = {0};
    flow_decode(&p, &s, frame, 11, 0);
    for (unsigned i = 0; i < 4; ++i) send_frame(&p, &s, 200 + i * 20, 7 + i, 3000 + i);
    assert(s.range_valid);
    uint32_t random = 1;
    for (unsigned i = 0; i < 200000; ++i) {
        random = random * 1664525u + 1013904223u;
        const uint8_t byte = random >> 24;
        flow_decode(&p, &s, &byte, 1, i);
        assert(p.used < MICOLINK_BYTES);
    }
}

static void test_flow_age(void)
{
    for (unsigned split = 1; split < sizeof(frame); ++split) {
        for (unsigned late = 0; late < 2; ++late) {
            FlowParser p = {0}; FlowSample s = {0};
            const uint32_t start = UINT32_MAX - FC_PERIOD_US;
            send_frame(&p, &s, 100, 1, start - 2 * FC_PERIOD_US);
            send_frame(&p, &s, 120, 2, start);
            /* Re-use the next complete packet, split at every byte boundary. */
            frame[4] = 3; frame[6] = 140; checksum();
            flow_decode(&p, &s, frame, split, start + FC_PERIOD_US);
            flow_decode(&p, &s, frame + split, sizeof(frame) - split,
                        start + FC_PERIOD_US + FC_FLOW_FRAME_MAX_US + late);
            assert(s.samples == (late ? 1u : 2u));
            assert(s.range_valid == !late && s.flow_valid == !late);
            assert(s.observed_us == (late ? start : start + FC_PERIOD_US));
        }
    }
    FlowParser p = {0}; FlowSample s = {0};
    send_frame(&p, &s, 100, 1, 1000);
    send_frame(&p, &s, 120, 2, 21000);
    flow_decode(&p, &s, NULL, 0, 21000 + FC_FLOW_MAX_AGE_US);
    assert(s.range_valid);
    flow_decode(&p, &s, NULL, 0, 21001 + FC_FLOW_MAX_AGE_US);
    assert(!s.range_valid && !s.flow_valid && !p.have_time);
    /* A full host-clock wrap must not revive expired validity or a fragment. */
    flow_decode(&p, &s, NULL, 0, 21000);
    assert(!s.range_valid && s.samples == 1);
    send_frame(&p, &s, 140, 3, 31000);
    assert(!s.range_valid && s.samples == 1);
    send_frame(&p, &s, 160, 4, 51000);
    assert(s.range_valid && s.samples == 2);
    const uint8_t noise[] = {0xef, 0}; /* Header noise must not refresh the source clock. */
    for (uint32_t now = 71000; now <= 151000; now += 20000)
        flow_decode(&p, &s, noise, sizeof(noise), now);
    send_frame(&p, &s, 180, 5, 171000);
    assert(!s.range_valid && s.samples == 2);
    send_frame(&p, &s, 200, 6, 191000);
    assert(s.range_valid && s.samples == 3);
    send_frame(&p, &s, 220, 7, 1000000); /* A queued frame after a receiver stall. */
    assert(!s.range_valid && !s.flow_valid && s.samples == 3);
    send_frame(&p, &s, 240, 8, 1020000);
    assert(s.range_valid && s.samples == 4);
    frame[4] = 9; frame[6] = 250; checksum();
    flow_decode(&p, &s, frame, 13, 1040000);
    flow_decode(&p, &s, NULL, 0, 1040001 + FC_FLOW_FRAME_MAX_US);
    assert(p.used == 0 && !s.range_valid);
    flow_decode(&p, &s, frame + 13, sizeof(frame) - 13, 1040000);
    assert(!s.range_valid && s.samples == 4);
}

int main(void)
{
    test_imu();
    test_flow();
    test_corruption();
    test_flow_age();
    printf("sensor decoding: units, norms, protocol, corruption, freshness and wrap passed\n");
    return 0;
}
