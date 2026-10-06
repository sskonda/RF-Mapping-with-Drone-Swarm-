#ifndef VOXEL_CORE_H
#define VOXEL_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { VM_SLOTS = 1024, VM_SIZE_MM = 500, VM_TX_BYTES = 28, VM_RX_BYTES = 32,
       VM_QUEUE = 32, VM_CACHE_BYTES = 64, VM_NEW = 1, VM_REJECTED = 2, VM_OVERFLOW = 4 };
enum { VM_WORD_BYTES = 4, VM_AXES = 3, VM_TX_RSSI = 12, VM_TX_DRONE = 16,
       VM_TX_TIME = 20, VM_RX_SUM = 4, VM_RX_COUNT = 12, VM_RX_FLAGS = 16,
       VM_RX_DRONE = 20, VM_RX_TIME = 24, VM_LATENCY_BINS = 16 };
typedef struct { int32_t position[3], rssi; uint32_t drone; uint64_t time_us; } vm_observation;
typedef struct { int64_t coordinate[3], sum; uint32_t count; bool occupied; } vm_slot;
typedef struct { vm_observation observation; uint32_t sequence; } vm_request;
typedef struct { uint32_t slot, flags, drone; uint64_t time_us; int64_t sum; uint32_t count; } vm_result;
typedef struct {
    uint64_t submitted, queued, dropped, started, completed, accepted, rejected;
    uint64_t errors, ambiguous, export_dropped, latency_total_us, latency_max_us;
    uint64_t latency_bins[VM_LATENCY_BINS];
} vm_counters;
typedef enum { VM_IDLE, VM_DMA_OWNED, VM_UNSYNCHRONIZED } vm_state;
typedef struct {
    void *context;
    void (*flush)(void *, void *, size_t);
    void (*invalidate)(void *, void *, size_t);
    int (*start_rx)(void *, void *, size_t);
    int (*start_tx)(void *, const void *, size_t);
    /* 0 pending, 1 both IOC+idle, -1 DMA error; length valid only on completion. */
    int (*poll)(void *, size_t *);
    void (*halt)(void *);
    void (*result)(void *, const vm_request *, const vm_result *, const vm_slot *);
} vm_io;
typedef struct {
    vm_slot slots[VM_SLOTS];
    vm_request queue[VM_QUEUE], pending;
    size_t head, depth, occupied;
    vm_state state;
    uint64_t started_us, deadline_us;
    vm_counters counters;
    _Alignas(VM_CACHE_BYTES) uint8_t tx[VM_CACHE_BYTES];
    _Alignas(VM_CACHE_BYTES) uint8_t rx[VM_CACHE_BYTES];
} vm_engine;
uint32_t vm_get32(const uint8_t *p);
uint64_t vm_get64(const uint8_t *p);
void vm_put32(uint8_t *p, uint32_t value);
void vm_put64(uint8_t *p, uint64_t value);
int64_t vm_coordinate(int32_t position, int32_t origin);
double vm_mean(const vm_slot *slot);
void vm_encode(uint8_t *data, const vm_observation *observation);
void vm_decode_observation(vm_observation *o, const uint8_t *data);
void vm_init(vm_engine *engine, uint64_t timeout_us);
bool vm_submit(vm_engine *engine, const vm_request *request);
bool vm_apply(vm_engine *engine, const uint8_t *data, size_t length, vm_result *result);
void vm_stop(vm_engine *engine, const vm_io *io);
void vm_service(vm_engine *engine, const vm_io *io, uint64_t now_us);
#endif
