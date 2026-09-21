#pragma once

#include <stdbool.h>
#include <stdint.h>

enum { BNO_DATA_BYTES = 20, BNO_STATUS_BYTES = 9, MICOLINK_BYTES = 27 };

typedef struct {
    float q[4]; /* w,x,y,z in the sensor's frame; no unverified body remap. */
    float gyro[3]; /* rad/s */
    uint32_t observed_us, samples;
    uint16_t revision;
    uint8_t calibration;
    bool valid;
} ImuSample;

typedef struct {
    uint32_t observed_us, device_ms, samples, rejected;
    float range_m;
    int16_t flow[2]; /* Micolink cm/s at 1 m; NOT body/world velocity. */
    uint8_t sequence, quality;
    bool range_valid, flow_valid;
} FlowSample;

typedef struct {
    ImuSample imu;
    FlowSample flow;
} Sensors;

typedef struct {
    uint8_t bytes[MICOLINK_BYTES], used;
    bool have_time;
} FlowParser;

bool imu_decode(ImuSample *sample, const uint8_t data[BNO_DATA_BYTES]);
bool imu_status_valid(const uint8_t status[BNO_STATUS_BYTES]);
void flow_decode(FlowParser *parser, FlowSample *sample, uint8_t byte, uint32_t now_us);
int sensors_init(Sensors *samples);
void sensors_poll(Sensors *samples, uint32_t now_us);
