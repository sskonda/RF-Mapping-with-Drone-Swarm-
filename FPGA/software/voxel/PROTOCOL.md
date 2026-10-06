# UART protocol v1

UART1: 115200, 8 data bits, no parity, one stop bit. No DMA interrupts or UART
interrupt handlers are required. No human-readable prints share the UART stream.

Each frame is `7e escaped(raw) 7e`. Raw `7e` or `7d` is encoded as `7d` followed
by byte XOR `20`. Other escape pairs are invalid. Empty boundary runs are ignored.
An oversized/invalid frame is discarded through its next boundary. Maximum raw
size is 148 bytes; maximum encoded size is 298. Parsers retain at most 148 bytes.

Raw fields, little endian:

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 1 | version = 1 |
| 1 | 1 | message type |
| 2 | 2 | payload length, 0..128 |
| 4 | 8 | nonzero host-selected session/epoch |
| 12 | 4 | sequence |
| 16 | length | payload |
| 16+length | 4 | CRC-32/ISO-HDLC over header and payload; reflected polynomial edb88320, init/final XOR ffffffff |

CRC detects accidental corruption, not adversarial modification. Header/session/
sequence are outside the unchanged DMA payload. START uses sequence zero and a
new random nonzero session, once per coordinated boot. Payload is u32 46524553
(the explicit fresh-map attestation token). A running application cannot rebind.
Sequences 1..ffffffff are consumed in exact order for input commands, including
commands rejected for a full queue. There is no sequence wrap in one session.
A missing frame creates a sequence gap; diagnostics expose errors and the host
stops on a missing result. Duplicates/out-of-order/wrong-session frames are ignored
and counted. A new session requires coordinated restart, not another START.

| Type | Direction | Payload |
|---|---|---|
| 1 START | host→PS | u32 fresh-map token |
| 2 OBSERVATION | host→PS | exactly the seven TX words (28 bytes) |
| 3 STATUS | host→PS | empty |
| 4 SNAPSHOT | host→PS | empty; requires idle synchronized engine and empty input queue |
| 128 RESULT | PS→host | 56-byte result below; same sequence as triggering observation |
| 129 DIAGNOSTIC | PS→host | 16 u64 counters/state fields below |
| 130 ACK | PS→host | u32 code, u32 free observation-queue entries |
| 131 SNAPSHOT_SLOT | PS→host | first 40 bytes of RESULT; one per occupied slot |
| 132 SNAPSHOT_END | PS→host | u32 occupied count; same sequence as snapshot request |
| 133 LATENCY | PS→host | 16 u64 elapsed-time histogram counters, emitted after STATUS |

ACK codes: 0 admitted, 1 observation dropped, 2 snapshot busy/unavailable,
3 malformed/unsupported command. An admission ACK is not hardware acceptance.
Each completed DMA observation produces RESULT, including hardware rejections.
Output overflow drops complete frames and increments `export_dropped`; partial
frames already being transmitted remain intact. Query STATUS or take a quiescent
snapshot to inspect a still-synchronized mirror after a viewer drop. The standard
live collector stops after any missing result because its own audit is incomplete.

RESULT offsets: slot u32 at 0; voxel x/y/z signed i64 at 4/12/20; sum signed i64
at 28; count u32 at 36; flags u32 at 40; triggering drone u32 at 44; acquisition
microseconds u64 at 48. Voxel lower corner = index × 0.5 metres. Mean is the exact
rational sum/count; JSON export additionally computes its fractional floating
representation. Rejected results carry the requested coordinates, not slot zero's
coordinates; never render them as an occupied update. Snapshot metadata is not a
last-drone ownership claim and is omitted.

DIAGNOSTIC fields in order: state (0 idle, 1 DMA-owned, 2 unsynchronized), queue
 depth, occupied, submitted, queued, dropped, started, completed, accepted,
rejected, errors, ambiguous, export_dropped, protocol+framing errors,
latency_total_us, latency_max_us. LATENCY bin 0 includes 0–1 us, bin k includes
2^k..2^(k+1)-1 us, and bin 15 includes all >=32768 us. Times measure the DMA
service interval, including polling delay, not just PL compute latency.

Accounting: `submitted = dropped + completed + ambiguous + queue_depth +
current_unambiguous_inflight`; `completed = accepted + rejected`. `queued` counts
successful software admission, not FPGA acceptance. Invalid/unrecognized serial
frames are counted as protocol errors rather than invented observations. PC raw
source drops and firmware export drops are separate counters. On a failure, the
pending observation contributes one ambiguous outcome; it cannot honestly be
classified as hardware accepted/rejected without a valid result.
