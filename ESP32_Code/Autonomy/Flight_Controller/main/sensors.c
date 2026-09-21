#include "sensors.h"
#include "config.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

enum {
    BNO_CHIP_ID = 0xa0, BNO_PAGE = 0x07, BNO_DATA = 0x14, BNO_STATUS = 0x35, BNO_INTERRUPT = 0x37,
    BNO_UNITS = 0x3b, BNO_MODE = 0x3d, BNO_CONFIG = 0, BNO_IMUPLUS = 8,
    BNO_RAD_S = 2, BNO_INT_ENABLE = 0x10, BNO_FUSION_READY = 1,
    BNO_DRDY_REVISION = 0x0314, BNO_BOOT_MS = 700, BNO_MODE_WAIT_MS = 20,
    FLOW_BUFFER_BYTES = 256, FLOW_READ_BYTES = 64, FLOW_EVENTS = 4
};
static i2c_master_dev_handle_t imu;
static QueueHandle_t flow_events;
static FlowParser parser;

static esp_err_t read_imu(uint8_t reg, void *data, unsigned size)
{
    return i2c_master_transmit_receive(imu, &reg, 1, data, size, FC_I2C_TIMEOUT_MS);
}

static esp_err_t write_imu(uint8_t reg, uint8_t value)
{
    const uint8_t data[] = {reg, value};
    return i2c_master_transmit(imu, data, sizeof(data), FC_I2C_TIMEOUT_MS);
}

#define TRY(call) do { esp_err_t error = (call); if (error != ESP_OK) return error; } while (0)

int sensors_init(Sensors *samples)
{
    TRY(gpio_set_level(FC_IMU_RESET, 0));
    TRY(gpio_set_direction(FC_IMU_RESET, GPIO_MODE_OUTPUT));
    vTaskDelay(pdMS_TO_TICKS(2));
    TRY(gpio_set_level(FC_IMU_RESET, 1));
    vTaskDelay(pdMS_TO_TICKS(BNO_BOOT_MS));
    const i2c_master_bus_config_t bus_config = {
        .i2c_port = 0, .sda_io_num = FC_I2C_SDA, .scl_io_num = FC_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7
    };
    i2c_master_bus_handle_t bus;
    TRY(i2c_new_master_bus(&bus_config, &bus));
    const i2c_device_config_t device = {
        .device_address = FC_IMU_ADDRESS, .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .scl_speed_hz = FC_I2C_HZ, .scl_wait_us = FC_I2C_STRETCH_US
    };
    TRY(i2c_master_bus_add_device(bus, &device, &imu));
    TRY(write_imu(BNO_PAGE, 0));
    uint8_t id[7];
    TRY(read_imu(0, id, sizeof(id)));
    if (id[0] != BNO_CHIP_ID) return ESP_ERR_NOT_FOUND;
    samples->imu.revision = id[4] | ((uint16_t)id[5] << 8);
    TRY(write_imu(BNO_MODE, BNO_CONFIG));
    vTaskDelay(pdMS_TO_TICKS(BNO_MODE_WAIT_MS));
    TRY(write_imu(BNO_UNITS, BNO_RAD_S));
    TRY(write_imu(BNO_PAGE, 1));
    TRY(write_imu(BNO_INT_ENABLE,
        samples->imu.revision >= BNO_DRDY_REVISION ? BNO_FUSION_READY : 0));
    TRY(write_imu(BNO_PAGE, 0));
    TRY(write_imu(BNO_MODE, BNO_IMUPLUS));
    vTaskDelay(pdMS_TO_TICKS(BNO_MODE_WAIT_MS));

    const uart_config_t uart = {
        .baud_rate = FC_FLOW_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT
    };
    TRY(uart_param_config(FC_FLOW_UART, &uart));
    TRY(uart_set_pin(FC_FLOW_UART, FC_FLOW_TX, FC_FLOW_RX,
                     UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    TRY(uart_driver_install(FC_FLOW_UART, FLOW_BUFFER_BYTES, 0, FLOW_EVENTS, &flow_events, 0));
    return ESP_OK;
}

void sensors_poll(Sensors *samples, uint32_t now_us)
{
    uint8_t status[BNO_STATUS_BYTES], data[BNO_DATA_BYTES], ready;
    ImuSample *s = &samples->imu;
    /* Latch expiry so a later 32-bit clock wrap cannot revive old data. */
    if (now_us - s->observed_us > FC_IMU_MAX_AGE_US) s->valid = false;
    if (read_imu(BNO_STATUS, status, sizeof(status)) != ESP_OK) {
        s->valid = false;
    } else {
        s->calibration = status[0];
        const bool status_ok = imu_status_valid(status);
        const bool supports_ready = s->revision >= BNO_DRDY_REVISION;
        if (!status_ok) s->valid = false;
        if (!supports_ready || (status[2] & BNO_FUSION_READY)) {
            const bool decoded = read_imu(BNO_DATA, data, sizeof(data)) == ESP_OK &&
                                 imu_decode(s, data);
            /* A DRDY arriving during the read may describe this same sample. */
            s->valid = decoded && status_ok && supports_ready &&
                       read_imu(BNO_INTERRUPT, &ready, 1) == ESP_OK;
            if (s->valid) {
                s->observed_us = now_us; /* DRDY observation, not a sensor timestamp. */
                ++s->samples;
            }
        }
    }

    bool bad_uart = false;
    uart_event_t event;
    for (unsigned i = 0; i < FLOW_EVENTS && xQueueReceive(flow_events, &event, 0); ++i) {
        if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL ||
            event.type == UART_PARITY_ERR || event.type == UART_FRAME_ERR) bad_uart = true;
    }
    size_t available = 0;
    if (uart_get_buffered_data_len(FC_FLOW_UART, &available) != ESP_OK) bad_uart = true;
    /* Discard backlogs rather than timestamp queued measurements as fresh. */
    if (available > MICOLINK_BYTES) bad_uart = true;
    if (available > FLOW_READ_BYTES) available = FLOW_READ_BYTES;
    uint8_t bytes[FLOW_READ_BYTES];
    const int count = available ? uart_read_bytes(FC_FLOW_UART, bytes, available, 0) : 0;
    if (bad_uart || count < 0) {
        samples->flow.range_valid = samples->flow.flow_valid = false;
        ++samples->flow.rejected;
        parser = (FlowParser){0};
    } else {
        flow_decode(&parser, &samples->flow, bytes, (unsigned)count, now_us);
    }
}
