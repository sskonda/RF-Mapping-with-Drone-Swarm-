#include "voxel_wire.h"
#include <string.h>
uint32_t vw_crc(const uint8_t *p, size_t length)
{
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1U) ? UINT32_C(0xedb88320) : 0U);
    }
    return ~crc;
}
size_t vw_encode(uint8_t *out, const vw_message *m)
{
    if (m->length > VW_PAYLOAD) return 0;
    uint8_t raw[VW_RAW];
    raw[0] = VW_VERSION; raw[1] = m->type;
    raw[2] = (uint8_t)m->length; raw[3] = 0;
    vm_put64(raw + 4, m->session); vm_put32(raw + 12, m->sequence);
    memcpy(raw + VW_HEADER, m->payload, m->length);
    size_t size = VW_HEADER + m->length;
    vm_put32(raw + size, vw_crc(raw, size)); size += VW_CRC;
    size_t n = 0; out[n++] = VW_BOUNDARY;
    for (size_t i = 0; i < size; ++i) {
        if (raw[i] == VW_BOUNDARY || raw[i] == VW_ESCAPE) { out[n++] = VW_ESCAPE; out[n++] = raw[i] ^ 32U; }
        else out[n++] = raw[i];
    }
    out[n++] = VW_BOUNDARY;
    return n;
}
bool vw_feed(vw_parser *p, uint8_t byte, vw_message *m)
{
    if (byte == VW_BOUNDARY) {
        bool valid = false;
        if (p->length || p->discard || p->escaped) {
            size_t n = p->length;
            if (!p->discard && !p->escaped && n >= VW_HEADER + VW_CRC &&
                p->raw[0] == VW_VERSION && p->raw[3] == 0 && p->raw[2] <= VW_PAYLOAD &&
                n == VW_HEADER + (size_t)p->raw[2] + VW_CRC &&
                vm_get32(p->raw + n - VW_CRC) == vw_crc(p->raw, n - VW_CRC)) {
                m->type = p->raw[1]; m->session = vm_get64(p->raw + 4);
                m->sequence = vm_get32(p->raw + 12); m->length = p->raw[2];
                memcpy(m->payload, p->raw + VW_HEADER, m->length); valid = true;
            } else ++p->errors;
        }
        p->length = 0; p->escaped = false; p->discard = false;
        return valid;
    }
    if (p->discard) return false;
    if (p->escaped) {
        if (byte != (VW_BOUNDARY ^ 32U) && byte != (VW_ESCAPE ^ 32U)) { p->discard = true; return false; }
        byte ^= 32U; p->escaped = false;
    } else if (byte == VW_ESCAPE) { p->escaped = true; return false; }
    if (p->length == VW_RAW) p->discard = true; else p->raw[p->length++] = byte;
    return false;
}
