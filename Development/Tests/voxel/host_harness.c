#include "voxel_app.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { GOLD_QUEUE = VM_QUEUE + 2 };
typedef struct { uint8_t tx[VM_TX_BYTES], rx[VM_RX_BYTES]; } vector;
typedef struct {
    va_app app;
    vector golden[GOLD_QUEUE];
    size_t head, depth;
    uint8_t *destination;
    uint8_t shadow[VM_RX_BYTES];
    uint64_t now, arrival, tx_done, rx_done;
    uint32_t rng;
    unsigned phase, emitted;
    int fault;
    bool halted;
    FILE *output;
} fixture;
static fixture f;
static uint32_t random_word(void)
{
    f.rng ^= f.rng << 13; f.rng ^= f.rng >> 17; f.rng ^= f.rng << 5; return f.rng;
}
static void flush(void *ctx, void *buffer, size_t size)
{
    (void)ctx;
    assert(size == VM_CACHE_BYTES && (uintptr_t)buffer % VM_CACHE_BYTES == 0);
    if (buffer == f.app.engine.tx) { assert(f.phase == 0); f.phase = 1; }
    else { assert(buffer == f.app.engine.rx && f.phase == 1); f.phase = 2; }
}
static int rx_start(void *ctx, void *buffer, size_t size)
{
    (void)ctx; assert(f.phase == 2 && size == VM_RX_BYTES);
    f.phase = 3; f.destination = buffer;
    memset(buffer, 0xa5, VM_RX_BYTES);
    return f.fault == 1 ? -1 : 0;
}
static int tx_start(void *ctx, const void *buffer, size_t size)
{
    (void)ctx; assert(f.phase == 3 && size == VM_TX_BYTES && f.depth);
    vector *v = &f.golden[f.head];
    assert(memcmp(buffer, v->tx, size) == 0);
    memcpy(f.shadow, v->rx, VM_RX_BYTES);
    f.arrival = f.now + 1U + random_word() % 11U;
    f.tx_done = f.now + 1U + random_word() % 17U;
    f.rx_done = f.arrival + 1U + random_word() % 53U;
    f.phase = 4;
    return f.fault == 2 ? -1 : 0;
}
static int poll(void *ctx, size_t *length)
{
    (void)ctx; assert(f.phase == 4);
    if (f.fault == 3) return -1;
    if (f.fault == 4 || f.now < f.tx_done || f.now < f.rx_done) return 0;
    f.phase = 5; *length = f.fault == 5 ? 28U : VM_RX_BYTES; return 1;
}
static void invalidate(void *ctx, void *buffer, size_t length)
{
    (void)ctx; assert(f.phase == 5 && buffer == f.destination && length == VM_CACHE_BYTES);
    memcpy(buffer, f.shadow, VM_RX_BYTES); f.phase = 6;
}
static void halt(void *ctx) { (void)ctx; f.halted = true; }
static void result(void *ctx, const vm_request *q, const vm_result *r, const vm_slot *s)
{
    (void)ctx; assert(f.phase == 6);
    const uint8_t *expected = f.golden[f.head].rx;
    assert(r->slot == vm_get32(expected) && r->flags == vm_get32(expected + 16));
    if (!(r->flags & VM_REJECTED)) {
        assert(s && s->sum == r->sum && s->count == r->count);
        assert(vm_mean(s) == (double)s->sum / s->count);
    }
    va_result(&f.app, q, r, s);
    f.head = (f.head + 1U) % GOLD_QUEUE; --f.depth; f.phase = 0;
}
static const vm_io io = {NULL, flush, invalidate, rx_start, tx_start, poll, halt, result};
static void input(const vw_message *m)
{
    uint8_t bytes[VW_FRAME]; size_t n = vw_encode(bytes, m);
    /* Fragmented one-byte delivery exercises the actual parser/application. */
    for (size_t i = 0; i < n; ++i) va_input(&f.app, bytes[i]);
}
static void setup(uint32_t seed)
{
    memset(&f, 0, sizeof(f)); f.rng = seed ? seed : 1;
    va_init(&f.app, 500);
    vw_message m = {.type = VW_START, .session = 123, .length = 4};
    vm_put32(m.payload, VA_FRESH_MAP_TOKEN); input(&m); assert(f.app.bound);
}
static void tick(bool consume)
{
    ++f.now; vm_service(&f.app.engine, &io, f.now); va_background(&f.app);
    if (consume) {
        uint8_t byte;
        for (unsigned n = 0; n < 64 && va_output(&f.app, &byte); ++n)
            if (f.output) assert(fputc(byte, f.output) != EOF);
    }
}
static void submit(vector v, uint32_t sequence)
{
    assert(f.depth < GOLD_QUEUE);
    f.golden[(f.head + f.depth) % GOLD_QUEUE] = v; ++f.depth;
    vw_message m = {.type = VW_OBSERVATION, .session = 123, .sequence = sequence, .length = VM_TX_BYTES};
    memcpy(m.payload, v.tx, VM_TX_BYTES); input(&m);
}
static vector first_vector(void)
{
    vector v = {{0}, {0}};
    vm_observation o = {{-1, -500, -501}, -63, UINT32_MAX, UINT64_MAX};
    vm_encode(v.tx, &o); vm_put64(v.rx + 4, (uint64_t)(int64_t)-63);
    vm_put32(v.rx + 12, 1); vm_put32(v.rx + 16, VM_NEW);
    vm_put32(v.rx + 20, o.drone); vm_put64(v.rx + 24, o.time_us); return v;
}
static void faults(void)
{
    assert(vm_coordinate(INT32_MIN, INT32_MAX) == -8589935);
    assert(vm_coordinate(-1, 0) == -1 && vm_coordinate(-500, 0) == -1);
    for (int fault = 1; fault <= 5; ++fault) {
        setup(7); f.fault = fault; submit(first_vector(), 1);
        for (unsigned i = 0; i < 600; ++i) tick(true);
        assert(f.halted && f.app.engine.state == VM_UNSYNCHRONIZED);
        assert(f.app.engine.occupied == 0 && f.app.engine.counters.ambiguous == 1);
        assert(f.app.engine.counters.started == 1 && f.app.engine.counters.completed == 0);
        assert(!vm_submit(&f.app.engine, &f.app.engine.pending));
    }
    for (unsigned mutation = 0; mutation < 8; ++mutation) {
        setup(8); vector v = first_vector();
        switch (mutation) {
        case 0: vm_put32(v.rx, VM_SLOTS); break;
        case 1: vm_put32(v.rx + 16, 8); break;
        case 2: vm_put32(v.rx + 12, 0); break;
        case 3: vm_put32(v.rx + 20, 3); break;
        case 4: vm_put64(v.rx + 24, 1); break;
        case 5: vm_put32(v.rx + 16, 0); break;
        case 6: vm_put32(v.rx + 16, 2); break;
        default: vm_put64(v.rx + 4, 0); break;
        }
        submit(v, 1); for (unsigned i = 0; i < 100; ++i) tick(true);
        assert(f.halted && f.app.engine.occupied == 0);
    }
    setup(9); submit(first_vector(), 1);
    for (unsigned i = 0; i < 100; ++i) tick(true);
    vm_slot old = f.app.engine.slots[0];
    vm_result r; assert(!vm_apply(&f.app.engine, first_vector().rx, VM_RX_BYTES, &r));
    assert(memcmp(&old, &f.app.engine.slots[0], sizeof(old)) == 0);
    /* Valid overflow response is nonmutating; hardware count narrowed only in RTL tests. */
    f.app.engine.state = VM_DMA_OWNED; f.app.engine.slots[0].count = UINT32_MAX;
    vector overflow = first_vector(); vm_put32(overflow.rx + 12, UINT32_MAX);
    vm_put32(overflow.rx + 16, VM_REJECTED | VM_OVERFLOW);
    assert(vm_apply(&f.app.engine, overflow.rx, VM_RX_BYTES, &r));
    assert(f.app.engine.slots[0].sum == old.sum);
    setup(10);
    vm_request q = {0};
    for (unsigned i = 0; i < VM_QUEUE + 5U; ++i) (void)vm_submit(&f.app.engine, &q);
    assert(f.app.engine.depth == VM_QUEUE && f.app.engine.counters.dropped == 5);
    vm_stop(&f.app.engine, &io);
    assert(f.app.engine.counters.submitted == f.app.engine.counters.dropped);
    setup(11);
    vw_message msg = {.type=VW_STATUS,.session=123,.sequence=1};
    input(&msg); input(&msg); msg.sequence=2; msg.session=124; input(&msg);
    assert(f.app.protocol_errors == 2);
    uint8_t bytes[VW_FRAME]; msg.session=123; size_t n=vw_encode(bytes,&msg); bytes[4]^=1;
    for (size_t i=0;i<n;++i) va_input(&f.app,bytes[i]);
    for (unsigned i=0;i<1000;++i) va_input(&f.app,1);
    va_input(&f.app,VW_BOUNDARY); assert(f.app.parser.errors == 2);
    for (uint32_t i=2;i<100;++i) { msg.sequence=i; input(&msg); }
    assert(f.app.output_depth == VA_OUTPUTS && f.app.engine.counters.export_dropped > 0);
    setup(12);
    /* Slow/disconnected export consumer cannot stop accepted DMA work. */
    for (uint32_t seq=1;seq<=40;++seq) {
        vector v=first_vector(); vm_put64(v.rx+4,(uint64_t)(-63*(int64_t)seq));
        vm_put32(v.rx+12,seq); vm_put32(v.rx+16,seq==1 ? VM_NEW : 0);
        submit(v,seq); while (f.depth) tick(false);
    }
    assert(f.app.engine.counters.completed==40 && f.app.engine.slots[0].count==40);
    assert(f.app.engine.counters.export_dropped>0 && f.app.output_depth==VA_OUTPUTS);
    /* A response from the previous operation cannot update the same slot again. */
    vector stale=first_vector();submit(stale,41);
    for (unsigned i=0;i<100;++i) tick(false);
    assert(f.app.engine.state==VM_UNSYNCHRONIZED && f.app.engine.slots[0].count==40);
    /* A new host session cannot rebind a running application. */
    vw_message restart={.type=VW_START,.session=456,.sequence=0,.length=4};
    vm_put32(restart.payload,VA_FRESH_MAP_TOKEN);input(&restart);assert(f.app.session==123);
    fprintf(stderr,"PASS fault, cache order, malformed response, negative floor, saturation, serial/session tests\n");
}
int main(int argc, char **argv)
{
    faults();
    if (argc == 1) return 0;
    assert(argc == 4);
    setup((uint32_t)strtoul(argv[3], NULL, 10));
    FILE *vectors = fopen(argv[1], "r"); f.output = fopen(argv[2], "wb"); assert(vectors && f.output);
    uint32_t sequence = 0; unsigned words[15];
    for (;;) {
        int got = fscanf(vectors, "%x", &words[0]); if (got == EOF) break; assert(got == 1);
        for (unsigned j = 1; j < 15; ++j) assert(fscanf(vectors, "%x", &words[j]) == 1);
        vector v;
        for (unsigned j = 0; j < 7; ++j) vm_put32(v.tx + 4U*j, words[j]);
        for (unsigned j = 0; j < 8; ++j) vm_put32(v.rx + 4U*j, words[7U+j]);
        while (f.app.engine.depth == VM_QUEUE) tick(true);
        submit(v, ++sequence);
        unsigned delay = random_word() % 23U;
        for (unsigned j = 0; j < delay; ++j) tick(true);
    }
    while (f.app.engine.depth || f.app.engine.state == VM_DMA_OWNED || f.app.output_depth) tick(true);
    vw_message snapshot = {.type=VW_SNAPSHOT,.session=123,.sequence=sequence+1U};
    input(&snapshot);
    while (f.app.snapshot_active || f.app.output_depth) tick(true);
    vw_message status = {.type=VW_STATUS,.session=123,.sequence=sequence+2U};
    input(&status); while (f.app.output_depth) tick(true);
    assert(f.app.engine.state == VM_IDLE && f.depth == 0 && !f.halted);
    const vm_counters *c = &f.app.engine.counters;
    assert(c->submitted == sequence && c->completed == sequence && c->started == sequence);
    assert(c->accepted + c->rejected == sequence && c->dropped == 0 && c->export_dropped == 0);
    fprintf(stderr,"PASS seed=%s submitted=%"PRIu64" completed=%"PRIu64" accepted=%"PRIu64" rejected=%"PRIu64" dropped=%"PRIu64" ticks=%"PRIu64" memory_bytes=%zu\n",argv[3],c->submitted,c->completed,c->accepted,c->rejected,c->dropped,f.now,sizeof(f));
    assert(fclose(vectors)==0 && fclose(f.output)==0); return 0;
}
