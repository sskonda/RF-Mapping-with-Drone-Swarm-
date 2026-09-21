#include "motors.h"
#include "config.h"
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "driver/mcpwm_prelude.h"
#include "esp_attr.h"
#include "freertos/FreeRTOS.h"

static mcpwm_gen_handle_t outputs[FC_MOTOR_COUNT];
static gptimer_handle_t lease_timer;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static bool expired;

static bool IRAM_ATTR lease_expired(gptimer_handle_t timer,
                                    const gptimer_alarm_event_data_t *event, void *context)
{
    (void)timer;
    (void)event;
    (void)context;
    portENTER_CRITICAL_ISR(&lock);
    expired = true;
    for (unsigned i = 0; i < FC_MOTOR_COUNT; ++i) mcpwm_generator_set_force_level(outputs[i], 0, true);
    portEXIT_CRITICAL_ISR(&lock);
    return false;
}

#define TRY(call) do { esp_err_t error = (call); if (error != ESP_OK) return error; } while (0)

int motors_init(void)
{
    static const int pins[FC_MOTOR_COUNT] = FC_MOTOR_PINS;
    const uint32_t period = FC_PWM_RESOLUTION_HZ / FC_PWM_HZ;
    for (unsigned i = 0; i < FC_MOTOR_COUNT; ++i) {
        TRY(gpio_set_level(pins[i], 0));
        TRY(gpio_set_direction(pins[i], GPIO_MODE_OUTPUT));
    }
    mcpwm_timer_handle_t pwm_timer;
    const mcpwm_timer_config_t timer = {
        .group_id = 0, .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = FC_PWM_RESOLUTION_HZ, .period_ticks = period,
        .count_mode = MCPWM_TIMER_COUNT_MODE_UP
    };
    TRY(mcpwm_new_timer(&timer, &pwm_timer));
    for (unsigned pair = 0; pair < FC_MOTOR_COUNT / 2; ++pair) {
        mcpwm_oper_handle_t operator;
        const mcpwm_operator_config_t op = {.group_id = 0};
        TRY(mcpwm_new_operator(&op, &operator));
        TRY(mcpwm_operator_connect_timer(operator, pwm_timer));
        for (unsigned side = 0; side < 2; ++side) {
            const unsigned i = pair * 2 + side;
            mcpwm_cmpr_handle_t comparator;
            const mcpwm_comparator_config_t compare = {.flags.update_cmp_on_tez = true};
            TRY(mcpwm_new_comparator(operator, &compare, &comparator));
            TRY(mcpwm_comparator_set_compare_value(comparator,
                period * FC_BENCH_DUTY_PERMILLE / 1000));
            const mcpwm_generator_config_t gen = {.gen_gpio_num = pins[i]};
            TRY(mcpwm_new_generator(operator, &gen, &outputs[i]));
            TRY(mcpwm_generator_set_force_level(outputs[i], 0, true));
            TRY(mcpwm_generator_set_action_on_timer_event(outputs[i],
                MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                            MCPWM_TIMER_EVENT_EMPTY, MCPWM_GEN_ACTION_HIGH)));
            TRY(mcpwm_generator_set_action_on_compare_event(outputs[i],
                MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP,
                                              comparator, MCPWM_GEN_ACTION_LOW)));
        }
    }
    const gptimer_config_t watchdog = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT, .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000
    };
    TRY(gptimer_new_timer(&watchdog, &lease_timer));
    const gptimer_event_callbacks_t callbacks = {.on_alarm = lease_expired};
    TRY(gptimer_register_event_callbacks(lease_timer, &callbacks, NULL));
    TRY(gptimer_enable(lease_timer));
    TRY(gptimer_start(lease_timer));
    TRY(mcpwm_timer_enable(pwm_timer));
    TRY(mcpwm_timer_start_stop(pwm_timer, MCPWM_TIMER_START_NO_STOP));
    return ESP_OK;
}

bool motors_write(int motor)
{
    bool ok = motor >= -1 && motor < FC_MOTOR_COUNT;
    portENTER_CRITICAL(&lock); /* Same-core timeout ISR cannot interleave output release. */
    if (motor >= 0 && ok) {
        uint64_t now;
        ok = !expired && gptimer_get_raw_count(lease_timer, &now) == ESP_OK;
        if (ok) {
            const gptimer_alarm_config_t alarm = {.alarm_count = now + FC_OUTPUT_LEASE_US};
            ok = gptimer_set_alarm_action(lease_timer, &alarm) == ESP_OK;
        }
    }
    for (unsigned i = 0; i < FC_MOTOR_COUNT; ++i) {
        if (outputs[i] && mcpwm_generator_set_force_level(outputs[i],
                ok && motor == (int)i ? -1 : 0, true) != ESP_OK) ok = false;
    }
    if (!ok) {
        for (unsigned i = 0; i < FC_MOTOR_COUNT; ++i)
            if (outputs[i]) mcpwm_generator_set_force_level(outputs[i], 0, true);
    }
    if (!ok || motor < 0) {
        if (lease_timer) gptimer_set_alarm_action(lease_timer, NULL);
        expired = false;
    }
    portEXIT_CRITICAL(&lock);
    return ok;
}
