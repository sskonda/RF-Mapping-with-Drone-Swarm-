#include "voxel_core.h"
#include <limits.h>
#include <string.h>

uint32_t vm_get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
uint64_t vm_get64(const uint8_t *p) { return vm_get32(p) | (uint64_t)vm_get32(p + 4) << 32; }
void vm_put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8U * i));
}
void vm_put64(uint8_t *p, uint64_t v) { vm_put32(p, (uint32_t)v); vm_put32(p + 4, (uint32_t)(v >> 32)); }
static int32_t signed32(uint32_t v)
{
    return v <= INT32_MAX ? (int32_t)v : -1 - (int32_t)(UINT32_MAX - v);
}
static int64_t signed64(uint64_t v)
{
    return v <= INT64_MAX ? (int64_t)v : -1 - (int64_t)(UINT64_MAX - v);
}
int64_t vm_coordinate(int32_t position, int32_t origin)
{
    int64_t delta = (int64_t)position - origin;
    int64_t quotient = delta / VM_SIZE_MM;
    return quotient - (delta % VM_SIZE_MM < 0 ? 1 : 0);
}
double vm_mean(const vm_slot *slot) { return slot->count ? (double)slot->sum / slot->count : 0.0; }
void vm_encode(uint8_t *data, const vm_observation *o)
{
    for (unsigned i = 0; i < VM_AXES; ++i) vm_put32(data + 4U * i, (uint32_t)o->position[i]);
    vm_put32(data + VM_TX_RSSI, (uint32_t)o->rssi);
    vm_put32(data + VM_TX_DRONE, o->drone);
    vm_put64(data + VM_TX_TIME, o->time_us);
}
void vm_decode_observation(vm_observation *o, const uint8_t *data)
{
    for (unsigned i = 0; i < VM_AXES; ++i) o->position[i] = signed32(vm_get32(data + 4U * i));
    o->rssi = signed32(vm_get32(data + VM_TX_RSSI));
    o->drone = vm_get32(data + VM_TX_DRONE);
    o->time_us = vm_get64(data + VM_TX_TIME);
}
void vm_init(vm_engine *e, uint64_t timeout_us)
{
    memset(e, 0, sizeof(*e));
    e->deadline_us = timeout_us;
}
bool vm_submit(vm_engine *e, const vm_request *request)
{
    ++e->counters.submitted;
    if (e->state == VM_UNSYNCHRONIZED || e->depth == VM_QUEUE) {
        ++e->counters.dropped;
        return false;
    }
    e->queue[(e->head + e->depth) % VM_QUEUE] = *request;
    ++e->depth;
    ++e->counters.queued;
    return true;
}
static bool same_key(const vm_slot *s, const int64_t *key)
{
    return s->occupied && memcmp(s->coordinate, key, sizeof(s->coordinate)) == 0;
}
bool vm_apply(vm_engine *e, const uint8_t *data, size_t length, vm_result *r)
{
    if (e->state != VM_DMA_OWNED || length != VM_RX_BYTES) return false;
    r->slot = vm_get32(data); r->sum = signed64(vm_get64(data + VM_RX_SUM));
    r->count = vm_get32(data + VM_RX_COUNT); r->flags = vm_get32(data + VM_RX_FLAGS);
    r->drone = vm_get32(data + VM_RX_DRONE); r->time_us = vm_get64(data + VM_RX_TIME);
    if (r->slot >= VM_SLOTS || r->drone != e->pending.observation.drone ||
        r->time_us != e->pending.observation.time_us ||
        (r->flags != 0 && r->flags != VM_NEW && r->flags != VM_REJECTED &&
         r->flags != (VM_REJECTED | VM_OVERFLOW))) return false;
    int64_t key[3];
    for (unsigned i = 0; i < VM_AXES; ++i) key[i] = vm_coordinate(e->pending.observation.position[i], 0);
    vm_slot *s = &e->slots[r->slot];
    if (r->flags == VM_REJECTED) {
        if (r->slot != 0 || r->sum != 0 || r->count != 0 || e->occupied != VM_SLOTS) return false;
        for (size_t i = 0; i < e->occupied; ++i) if (same_key(&e->slots[i], key)) return false;
        return true;
    }
    if (r->flags & VM_OVERFLOW)
        return same_key(s, key) && s->count == UINT32_MAX && r->count == s->count && r->sum == s->sum;
    if (r->count == 0) return false;
    if (r->flags == VM_NEW) {
        if (s->occupied || r->slot != e->occupied || r->count != 1 || r->sum != e->pending.observation.rssi) return false;
        for (size_t i = 0; i < e->occupied; ++i) if (same_key(&e->slots[i], key)) return false;
    } else {
        int64_t delta = e->pending.observation.rssi;
        if (!same_key(s, key) || s->count == UINT32_MAX || r->count != s->count + 1U ||
            (delta > 0 && s->sum > INT64_MAX - delta) ||
            (delta < 0 && s->sum < INT64_MIN - delta) || r->sum != s->sum + delta) return false;
    }
    if (!s->occupied) ++e->occupied;
    memcpy(s->coordinate, key, sizeof(key));
    s->sum = r->sum; s->count = r->count; s->occupied = true;
    return true;
}
void vm_stop(vm_engine *e, const vm_io *io)
{
    if (e->state == VM_UNSYNCHRONIZED) return;
    if (e->state == VM_DMA_OWNED) ++e->counters.ambiguous;
    ++e->counters.errors;
    e->counters.dropped += e->depth;
    e->depth = 0;
    e->state = VM_UNSYNCHRONIZED;
    io->halt(io->context);
    /* DMA may still own the buffers: never reuse them until coordinated restart. */
}
void vm_service(vm_engine *e, const vm_io *io, uint64_t now_us)
{
    if (e->state == VM_UNSYNCHRONIZED) return;
    if (e->state == VM_DMA_OWNED) {
        size_t length = 0;
        int status = io->poll(io->context, &length);
        if (status < 0 || now_us - e->started_us >= e->deadline_us) { vm_stop(e, io); return; }
        if (status == 0) return;
        if (length != VM_RX_BYTES) { vm_stop(e, io); return; }
        io->invalidate(io->context, e->rx, sizeof(e->rx));
        vm_result r;
        if (!vm_apply(e, e->rx, length, &r)) { vm_stop(e, io); return; }
        ++e->counters.completed;
        if (r.flags & VM_REJECTED) ++e->counters.rejected; else ++e->counters.accepted;
        uint64_t latency = now_us - e->started_us;
        e->counters.latency_total_us += latency;
        if (latency > e->counters.latency_max_us) e->counters.latency_max_us = latency;
        unsigned bin = 0;
        for (uint64_t v = latency; v > 1 && bin + 1U < VM_LATENCY_BINS; v >>= 1) ++bin;
        ++e->counters.latency_bins[bin];
        e->state = VM_IDLE;
        io->result(io->context, &e->pending, &r, r.flags & VM_REJECTED ? NULL : &e->slots[r.slot]);
    }
    if (e->depth == 0) return;
    e->pending = e->queue[e->head]; e->head = (e->head + 1U) % VM_QUEUE; --e->depth;
    vm_encode(e->tx, &e->pending.observation);
    io->flush(io->context, e->tx, sizeof(e->tx));
    io->flush(io->context, e->rx, sizeof(e->rx));
    e->state = VM_DMA_OWNED; e->started_us = now_us; ++e->counters.started;
    if (io->start_rx(io->context, e->rx, VM_RX_BYTES) != 0 ||
        io->start_tx(io->context, e->tx, VM_TX_BYTES) != 0) vm_stop(e, io);
}
