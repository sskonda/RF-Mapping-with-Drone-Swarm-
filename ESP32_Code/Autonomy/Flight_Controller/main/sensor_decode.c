#include "sensors.h"
#include "config.h"
#include <math.h>

enum { MICOLINK_HEAD = 0xef, MICOLINK_DEVICE = 0x0f, MICOLINK_SYSTEM = 0,
       MICOLINK_RANGE = 0x51, MICOLINK_PAYLOAD = 20, MICOLINK_HEADER = 6,
       MICOLINK_CHECKSUM = MICOLINK_BYTES - 1, MICOLINK_SEQUENCE = 4,
       RANGE_MM = 4, TOF_STATUS = 10, FLOW_X = 12, FLOW_Y = 14,
       FLOW_QUALITY = 16, FLOW_STATUS = 17, SENSOR_VALID = 1,
       FLOW_SOURCE_GAP_MS = 200, SEQUENCE_HALF_RANGE = 128 };

bool imu_status_valid(const uint8_t status[BNO_STATUS_BYTES])
{
    enum { CALIBRATION = 0, SELF_TEST = 1, SYSTEM_STATUS = 4, SYSTEM_ERROR = 5,
           UNITS = 6, MODE = 8, REQUIRED_CALIBRATION = 0x3c, REQUIRED_SELF_TEST = 0x0d,
           FUSION_RUNNING = 5, RAD_S = 2, IMUPLUS = 8 };
    return (status[CALIBRATION] & REQUIRED_CALIBRATION) == REQUIRED_CALIBRATION &&
           (status[SELF_TEST] & REQUIRED_SELF_TEST) == REQUIRED_SELF_TEST &&
           status[SYSTEM_STATUS] == FUSION_RUNNING && status[SYSTEM_ERROR] == 0 &&
           status[UNITS] == RAD_S && status[MODE] == IMUPLUS;
}

static int16_t signed_le16(const uint8_t *p)
{
    int32_t value = p[0] | ((uint32_t)p[1] << 8);
    return (int16_t)(value >= 32768 ? value - 65536 : value);
}

static uint32_t le32(const uint8_t *p)
{
    return p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

bool imu_decode(ImuSample *sample, const uint8_t data[BNO_DATA_BYTES])
{
    const float quaternion_scale = 1.0f / 16384.0f, gyro_scale = 1.0f / 900.0f;
    const unsigned quaternion_offset = 12; /* Skip gyro and Euler registers. */
    float norm2 = 0.0f;
    for (unsigned i = 0; i < 4; ++i) {
        sample->q[i] = signed_le16(data + quaternion_offset + 2 * i) * quaternion_scale;
        norm2 += sample->q[i] * sample->q[i];
    }
    if (!(norm2 > 0.9f && norm2 < 1.1f)) return false;
    const float inverse_norm = 1.0f / sqrtf(norm2);
    for (unsigned i = 0; i < 4; ++i) sample->q[i] *= inverse_norm;
    for (unsigned i = 0; i < 3; ++i) sample->gyro[i] = signed_le16(data + 2 * i) * gyro_scale;
    return true;
}

void flow_decode(FlowParser *parser, FlowSample *sample, const uint8_t *bytes,
                 unsigned count, uint32_t now_us)
{
    static const uint8_t header[MICOLINK_HEADER] = {
        MICOLINK_HEAD, MICOLINK_DEVICE, MICOLINK_SYSTEM, MICOLINK_RANGE, 0, MICOLINK_PAYLOAD
    };
    if (now_us - sample->observed_us > FC_FLOW_MAX_AGE_US)
        sample->range_valid = sample->flow_valid = false;
    if (now_us - parser->received_us > FC_FLOW_MAX_AGE_US) parser->have_time = false;
    if (parser->used && now_us - parser->started_us > FC_FLOW_FRAME_MAX_US) {
        parser->used = 0;
        sample->range_valid = sample->flow_valid = false;
        ++sample->rejected;
    }
    for (unsigned n = 0; n < count; ++n) {
        const uint8_t byte = bytes[n];
        if (parser->used < MICOLINK_HEADER && parser->used != MICOLINK_SEQUENCE && byte != header[parser->used]) {
            parser->used = 0;
            if (byte != MICOLINK_HEAD) continue;
        }
        if (!parser->used) parser->started_us = now_us;
        parser->bytes[parser->used++] = byte;
        if (parser->used != MICOLINK_BYTES) continue;
        parser->used = 0;
        uint8_t checksum = 0;
        for (unsigned i = 0; i < MICOLINK_CHECKSUM; ++i) checksum += parser->bytes[i];
        sample->range_valid = sample->flow_valid = false;
        if (checksum != byte) {
            ++sample->rejected;
            continue;
        }
        const uint8_t *payload = parser->bytes + MICOLINK_HEADER;
        const uint32_t device_ms = le32(payload);
        const uint32_t elapsed_ms = device_ms - sample->device_ms;
        const uint8_t sequence = parser->bytes[MICOLINK_SEQUENCE];
        const uint8_t advance = sequence - sample->sequence;
        const bool advancing = parser->have_time && elapsed_ms > 0 && elapsed_ms <= FLOW_SOURCE_GAP_MS &&
                               advance > 0 && advance < SEQUENCE_HALF_RANGE;
        parser->have_time = true;
        parser->received_us = now_us;
        sample->device_ms = device_ms;
        sample->sequence = sequence;
        if (!advancing) {
            ++sample->rejected;
            continue; /* Rebase on reset; require another advancing frame. */
        }
        sample->observed_us = parser->started_us;
        ++sample->samples;
        sample->range_m = (float)le32(payload + RANGE_MM) * 0.001f;
        sample->flow[0] = signed_le16(payload + FLOW_X);
        sample->flow[1] = signed_le16(payload + FLOW_Y);
        sample->quality = payload[FLOW_QUALITY];
        sample->range_valid = payload[TOF_STATUS] == SENSOR_VALID &&
            sample->range_m >= FC_RANGE_MIN_M && sample->range_m <= FC_RANGE_MAX_M;
        sample->flow_valid = payload[FLOW_STATUS] == SENSOR_VALID && sample->quality >= FC_FLOW_MIN_QUALITY &&
            sample->flow[0] >= -FC_FLOW_MAX_CM_S_AT_1M && sample->flow[0] <= FC_FLOW_MAX_CM_S_AT_1M &&
            sample->flow[1] >= -FC_FLOW_MAX_CM_S_AT_1M && sample->flow[1] <= FC_FLOW_MAX_CM_S_AT_1M;
    }
}
