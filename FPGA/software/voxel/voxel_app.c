#include "voxel_app.h"
#include <string.h>
static bool emit(va_app *a, const vw_message *m)
{
    if (a->output_depth == VA_OUTPUTS) { ++a->engine.counters.export_dropped; return false; }
    va_frame *f = &a->output[(a->output_head + a->output_depth) % VA_OUTPUTS];
    f->length = vw_encode(f->bytes, m); f->offset = 0; ++a->output_depth;
    return true;
}
static void ack(va_app *a, uint32_t seq, uint32_t code)
{
    vw_message m = {.type = VW_ACK, .session = a->session, .sequence = seq, .length = 8};
    vm_put32(m.payload, code); vm_put32(m.payload + 4, (uint32_t)(VM_QUEUE - a->engine.depth));
    (void)emit(a, &m);
}
static void status(va_app *a, uint32_t seq)
{
    const vm_counters *c = &a->engine.counters;
    uint64_t values[] = {a->engine.state, a->engine.depth, a->engine.occupied,
        c->submitted, c->queued, c->dropped, c->started, c->completed, c->accepted,
        c->rejected, c->errors, c->ambiguous, c->export_dropped,
        a->protocol_errors + a->parser.errors, c->latency_total_us, c->latency_max_us};
    vw_message m = {.type = VW_DIAGNOSTIC, .session = a->session, .sequence = seq, .length = sizeof(values)};
    for (size_t i = 0; i < sizeof(values)/sizeof(values[0]); ++i) vm_put64(m.payload + 8U*i, values[i]);
    (void)emit(a, &m);
    m.type = VW_LATENCY;
    for (size_t i = 0; i < 16; ++i) vm_put64(m.payload + 8U*i, c->latency_bins[i]);
    (void)emit(a, &m);
}
void va_init(va_app *a, uint64_t timeout_us)
{
    memset(a, 0, sizeof(*a)); vm_init(&a->engine, timeout_us); a->next_sequence = 1;
}
static void receive(va_app *a, const vw_message *m)
{
    if (!a->bound) {
        if (m->type != VW_START || m->sequence != 0 || m->session == 0 || m->length != 4 ||
            vm_get32(m->payload) != VA_FRESH_MAP_TOKEN) { ++a->protocol_errors; return; }
        a->session = m->session; a->bound = true; ack(a, 0, 0); return;
    }
    if (m->session != a->session || a->sequence_exhausted || m->sequence != a->next_sequence) {
        ++a->protocol_errors; return;
    }
    if (a->next_sequence == UINT32_MAX) a->sequence_exhausted = true; else ++a->next_sequence;
    switch (m->type) {
    case VW_OBSERVATION: {
        if (m->length != VM_TX_BYTES) break;
        vm_request r = {.sequence = m->sequence};
        vm_decode_observation(&r.observation, m->payload);
        if (a->snapshot_active) {
            ++a->engine.counters.submitted; ++a->engine.counters.dropped; ack(a, m->sequence, 1);
        } else ack(a, m->sequence, vm_submit(&a->engine, &r) ? 0U : 1U);
        return;
    }
    case VW_STATUS:
        if (m->length != 0) break;
        status(a, m->sequence); return;
    case VW_SNAPSHOT:
        if (m->length != 0) break;
        if (a->engine.state != VM_IDLE || a->engine.depth || a->snapshot_active) { ack(a, m->sequence, 2); return; }
        a->snapshot_active = true; a->snapshot_slot = 0; a->snapshot_sequence = m->sequence;
        ack(a, m->sequence, 0); return;
    default: break;
    }
    ++a->protocol_errors; ack(a, m->sequence, 3);
}
void va_input(va_app *a, uint8_t byte)
{
    vw_message message;
    if (vw_feed(&a->parser, byte, &message)) receive(a, &message);
}
bool va_output(va_app *a, uint8_t *byte)
{
    if (!a->output_depth) return false;
    va_frame *f = &a->output[a->output_head];
    *byte = f->bytes[f->offset++];
    if (f->offset == f->length) { a->output_head = (a->output_head + 1U) % VA_OUTPUTS; --a->output_depth; }
    return true;
}
static void slot_payload(uint8_t *p, uint32_t index, const vm_slot *s)
{
    vm_put32(p, index);
    for (unsigned i = 0; i < 3; ++i) vm_put64(p + 4U + 8U*i, (uint64_t)s->coordinate[i]);
    vm_put64(p + 28, (uint64_t)s->sum); vm_put32(p + 36, s->count);
}
void va_result(va_app *a, const vm_request *q, const vm_result *r, const vm_slot *s)
{
    vw_message m = {.type = VW_RESULT, .session = a->session, .sequence = q->sequence, .length = 56};
    vm_slot rejected = {.sum = r->sum, .count = r->count};
    for (unsigned i = 0; i < 3; ++i) rejected.coordinate[i] = vm_coordinate(q->observation.position[i], 0);
    slot_payload(m.payload, r->slot, s ? s : &rejected);
    vm_put32(m.payload + 40, r->flags); vm_put32(m.payload + 44, r->drone); vm_put64(m.payload + 48, r->time_us);
    (void)emit(a, &m);
}
void va_background(va_app *a)
{
    if (!a->snapshot_active || a->output_depth == VA_OUTPUTS) return;
    vw_message m = {.type = VW_SNAPSHOT_SLOT, .session = a->session, .sequence = a->snapshot_sequence, .length = 40};
    if (a->snapshot_slot < a->engine.occupied) {
        slot_payload(m.payload, (uint32_t)a->snapshot_slot, &a->engine.slots[a->snapshot_slot]);
        (void)emit(a, &m); ++a->snapshot_slot;
    } else {
        m.type = VW_SNAPSHOT_END; m.length = 4;
        vm_put32(m.payload, (uint32_t)a->engine.occupied); (void)emit(a, &m); a->snapshot_active = false;
    }
}
