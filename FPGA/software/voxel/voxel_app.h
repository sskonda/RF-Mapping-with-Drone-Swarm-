#ifndef VOXEL_APP_H
#define VOXEL_APP_H
#include "voxel_wire.h"
enum { VA_OUTPUTS = 16, VA_UART_BUDGET = 64, VA_FRESH_MAP_TOKEN = 0x46524553 };
typedef struct {
    uint8_t bytes[VW_FRAME]; size_t length, offset;
} va_frame;
typedef struct {
    vm_engine engine;
    vw_parser parser;
    va_frame output[VA_OUTPUTS];
    size_t output_head, output_depth, snapshot_slot;
    uint64_t session, protocol_errors;
    uint32_t next_sequence, snapshot_sequence;
    bool bound, snapshot_active, sequence_exhausted;
} va_app;
void va_init(va_app *app, uint64_t timeout_us);
void va_input(va_app *app, uint8_t byte);
bool va_output(va_app *app, uint8_t *byte);
void va_result(va_app *app, const vm_request *request, const vm_result *result, const vm_slot *slot);
void va_background(va_app *app);
#endif
