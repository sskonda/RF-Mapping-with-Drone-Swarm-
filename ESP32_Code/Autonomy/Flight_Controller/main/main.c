#include "bench.h"
#include "config.h"
#include "motors.h"
#include "sensors.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <unistd.h>

_Static_assert(CONFIG_FREERTOS_HZ == 1000 && CONFIG_ESP_MAIN_TASK_AFFINITY == 0,
               "Bench timing requires a 1 ms tick and a core-0 console");

typedef struct {
    Sensors sensors;
    uint64_t execution_sum_us;
    uint32_t now_us, cycles, worst_us, jitter_us, misses;
    int init_error, motor;
    ArmState state;
    BenchFault fault;
} Telemetry;

static TaskHandle_t flight;
static portMUX_TYPE mailbox_lock = portMUX_INITIALIZER_UNLOCKED;
static struct {
    Telemetry telemetry;
    BenchCommand command;
    bool telemetry_ready;
} mailbox;

static void publish(const Telemetry *t)
{
    portENTER_CRITICAL(&mailbox_lock);
    mailbox.telemetry = *t;
    mailbox.telemetry_ready = true;
    portEXIT_CRITICAL(&mailbox_lock);
}

static void stop_bench(Bench *bench)
{
    motors_write(-1);
    bench_stop(bench, BENCH_STOP);
    portENTER_CRITICAL(&mailbox_lock);
    mailbox.command.key = 0; /* A stop also discards any queued arm/pulse. */
    portEXIT_CRITICAL(&mailbox_lock);
}

static void flight_task(void *argument)
{
    (void)argument;
    Telemetry t = {0};
    Bench bench = {.motor = -1};
    t.init_error = motors_init();
    if (!t.init_error) t.init_error = sensors_init(&t.sensors);
    if (!t.init_error) t.init_error = esp_task_wdt_add(NULL);
    if (t.init_error) {
        motors_write(-1);
        t.motor = -1;
        publish(&t);
        vTaskSuspend(NULL); /* Reboot required; no allocation/reinitialization in the loop. */
    }
    TickType_t target = xTaskGetTickCount();
    uint32_t previous_start = 0, report_count = 0;
    const TickType_t period_ticks = pdMS_TO_TICKS(FC_PERIOD_US / 1000);
    for (;;) {
        TickType_t tick = xTaskGetTickCount();
        while ((int32_t)(target - tick) > 0) {
            if (ulTaskNotifyTake(pdTRUE, target - tick)) stop_bench(&bench);
            tick = xTaskGetTickCount();
        }
        if (ulTaskNotifyTake(pdTRUE, 0)) stop_bench(&bench);
        const uint32_t start = (uint32_t)esp_timer_get_time();
        uint32_t jitter = 0;
        if (t.cycles) {
            const uint32_t period = start - previous_start;
            jitter = period > FC_PERIOD_US ? period - FC_PERIOD_US : FC_PERIOD_US - period;
        }
        previous_start = start;
        if (jitter > t.jitter_us) t.jitter_us = jitter;
        bool deadline_bad = jitter > FC_JITTER_LIMIT_US;
        if (deadline_bad) {
            motors_write(-1);
            bench_stop(&bench, BENCH_DEADLINE);
        }
        sensors_poll(&t.sensors, start);
        const bool stopped = ulTaskNotifyTake(pdTRUE, 0) != 0;
        if (stopped) stop_bench(&bench);
        portENTER_CRITICAL(&mailbox_lock);
        BenchCommand cmd = mailbox.command;
        mailbox.command.key = 0;
        portEXIT_CRITICAL(&mailbox_lock);
        if (stopped) cmd.key = 'd';
        const uint32_t before_output = (uint32_t)esp_timer_get_time();
        deadline_bad |= before_output - start > FC_EXECUTION_BUDGET_US;
        if (deadline_bad) bench_stop(&bench, BENCH_DEADLINE);
        else bench_step(&bench, &t.sensors, &cmd, before_output, FC_BENCH_ENABLE);
        if (!motors_write(bench.motor)) bench_stop(&bench, BENCH_OUTPUT);
        if (esp_task_wdt_reset() != 0) {
            motors_write(-1);
            bench_stop(&bench, BENCH_OUTPUT);
        }
        if (++report_count == FC_REPORT_LOOPS) {
            report_count = 0;
            t.now_us = before_output;
            t.state = bench.state;
            t.fault = bench.fault;
            t.motor = bench.motor;
            publish(&t);
        }
        const uint32_t execution = (uint32_t)esp_timer_get_time() - start;
        ++t.cycles;
        t.execution_sum_us += execution;
        if (execution > t.worst_us) t.worst_us = execution;
        if (execution > FC_EXECUTION_BUDGET_US) {
            motors_write(-1);
            bench_stop(&bench, BENCH_DEADLINE);
            deadline_bad = true;
        }
        if (deadline_bad) ++t.misses;
        target += period_ticks;
        tick = xTaskGetTickCount();
        if ((int32_t)(tick - target) >= 0) target = tick + period_ticks;
    }
}

void app_main(void)
{
    static StaticTask_t flight_tcb;
    static StackType_t stack[FC_FLIGHT_STACK_BYTES / sizeof(StackType_t)];
    flight = xTaskCreateStaticPinnedToCore(flight_task, "flight", sizeof(stack), NULL,
                                         FC_FLIGHT_PRIORITY, stack, &flight_tcb, FC_FLIGHT_CORE);
    if (!flight) return;
    fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
    printf("BENCH ONLY enable=%d; a=arm, 1/2/3/4=FL/FR/RR/RL pulse, d or !=stop.\n",
           FC_BENCH_ENABLE);
    Telemetry t;
    for (;;) {
        char key;
        for (unsigned i = 0; i < 16 && read(STDIN_FILENO, &key, 1) == 1; ++i) {
            if (key == '\r' || key == '\n') continue;
            if (key == 'a' || (key >= '1' && key < '1' + FC_MOTOR_COUNT)) {
                const BenchCommand cmd = {.issued_us = (uint32_t)esp_timer_get_time(), .key = key};
                portENTER_CRITICAL(&mailbox_lock);
                const bool occupied = mailbox.command.key != 0;
                if (!occupied) mailbox.command = cmd;
                portEXIT_CRITICAL(&mailbox_lock);
                if (occupied) xTaskNotifyGive(flight);
            } else {
                xTaskNotifyGive(flight); /* Stop cannot be overwritten by a later command. */
            }
        }
        portENTER_CRITICAL(&mailbox_lock);
        const bool ready = mailbox.telemetry_ready;
        if (ready) t = mailbox.telemetry;
        mailbox.telemetry_ready = false;
        portEXIT_CRITICAL(&mailbox_lock);
        if (ready) {
            const ImuSample *imu = &t.sensors.imu;
            const FlowSample *flow = &t.sensors.flow;
            printf("state=%d fault=%d motor=%d init=%d rev=%04x cal=%02x "
                   "valid=%d/%d/%d age_us=%"PRIu32"/%"PRIu32" samples=%"PRIu32"/%"PRIu32
                   " reject=%"PRIu32" exec_avg/max_us=%"PRIu64"/%"PRIu32
                   " jitter_us=%"PRIu32" misses=%"PRIu32" stack_free=%u\n",
                   t.state, t.fault, t.motor, t.init_error, imu->revision, imu->calibration,
                   imu->valid, flow->range_valid, flow->flow_valid,
                   t.now_us - imu->observed_us, t.now_us - flow->observed_us,
                   imu->samples, flow->samples, flow->rejected,
                   t.cycles ? t.execution_sum_us / t.cycles : 0, t.worst_us,
                   t.jitter_us, t.misses, (unsigned)uxTaskGetStackHighWaterMark(flight));
            printf("q=%.4f,%.4f,%.4f,%.4f gyro_rad_s=%.3f,%.3f,%.3f "
                   "range_m=%.3f flow_cm_s_at_1m=%d,%d quality=%u device_ms=%"PRIu32"\n",
                   (double)imu->q[0], (double)imu->q[1], (double)imu->q[2], (double)imu->q[3],
                   (double)imu->gyro[0], (double)imu->gyro[1], (double)imu->gyro[2],
                   (double)flow->range_m, flow->flow[0], flow->flow[1], flow->quality, flow->device_ms);
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}
