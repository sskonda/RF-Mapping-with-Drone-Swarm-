#pragma once

#include "sensors.h"

typedef enum { DISARMED, ARMED } ArmState;
typedef enum { BENCH_OK, BENCH_STOP, BENCH_LOCKED, BENCH_SENSOR, BENCH_COMMAND,
               BENCH_TIMEOUT, BENCH_MOTION, BENCH_DEADLINE, BENCH_OUTPUT } BenchFault;
typedef struct { uint32_t issued_us; char key; } BenchCommand;
typedef struct {
    float reference_q[4];
    uint32_t armed_us, pulse_us;
    int motor; /* -1 is all off; 0..3 is the configured FL,FR,RR,RL channel. */
    ArmState state;
    BenchFault fault;
} Bench;

void bench_stop(Bench *bench, BenchFault fault);
void bench_step(Bench *bench, const Sensors *sensors, const BenchCommand *command,
                uint32_t now_us, bool enabled);
