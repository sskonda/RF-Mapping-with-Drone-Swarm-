#ifndef VOXEL_WIRE_H
#define VOXEL_WIRE_H
#include "voxel_core.h"
enum { VW_VERSION = 1, VW_PAYLOAD = 128, VW_HEADER = 16, VW_CRC = 4,
       VW_RAW = VW_HEADER + VW_PAYLOAD + VW_CRC, VW_FRAME = 2 * VW_RAW + 2,
       VW_BOUNDARY = 126, VW_ESCAPE = 125, VW_START = 1, VW_OBSERVATION = 2,
       VW_STATUS = 3, VW_SNAPSHOT = 4, VW_RESULT = 128, VW_DIAGNOSTIC = 129,
       VW_ACK = 130, VW_SNAPSHOT_SLOT = 131, VW_SNAPSHOT_END = 132, VW_LATENCY = 133 };
typedef struct { uint8_t type; uint64_t session; uint32_t sequence; size_t length; uint8_t payload[VW_PAYLOAD]; } vw_message;
typedef struct { uint8_t raw[VW_RAW]; size_t length; bool escaped, discard; uint64_t errors; } vw_parser;
uint32_t vw_crc(const uint8_t *data, size_t length);
size_t vw_encode(uint8_t *out, const vw_message *message);
bool vw_feed(vw_parser *parser, uint8_t byte, vw_message *message);
#endif
