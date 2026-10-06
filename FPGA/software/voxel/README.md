# Continuous RF voxel acquisition

This standalone C application targets Zybo Z7-20 / Zynq-7000 using Vitis 2024.2
and the unchanged `FPGA/bitstreams/voxel_readout_with_droneID.xsa`.
The working firmware reference remains
`FPGA/vitis_code/main_voxel_dma_droneID_readout_test.c`.
The software and RTL have host/simulation evidence; vendor compilation and board
operation are pending. See [fresh results](../../../Development/Reports/voxel/RESULTS.md).

## Architecture and hardware contract

`voxel_core.[ch]` owns a fixed DDR mirror, bounded observation queue, pending
observation and DMA ownership state. `voxel_wire.[ch]` handles framing/CRC.
`voxel_app.[ch]` handles sessions, commands, bounded output and quiescent snapshots.
`zybo_main.c` is the small polling DMA/cache/UART/time adapter. The Python
`rf_mapping.voxel` package handles acquisition, pose joins, replay and rendering.
There is no dynamic allocation in the firmware. The host mock fixture occupies
about 50 KiB; actual ARM layout and DDR placement must be checked after linking.

The top-level XSA `design_1.hwh` agrees with current wrapper parameters:

| Item | Contract |
|---|---|
| TX | 7 little-endian words: signed x/y/z mm, signed RSSI dBm, unsigned drone ID, timestamp low/high; 28 bytes; TLAST at word 6 |
| RX | 8 words: slot, signed 64-bit sum low/high, unsigned count, flags, drone ID, timestamp low/high; 32 bytes; TLAST at word 7 |
| Flags | new bit 0; rejected bit 1; overflow bit 2 |
| Grid | origins 0; 500 mm; 1,024 slots; 2,048 lookup buckets |
| DMA | simple mode; 32-bit streams; no SG/DRE; memory interfaces are 64-bit |
| Clock/UART | configured 100 MHz PL; PS UART1 on MIO48–49; 115200 baud initially |

HWH confirms configuration/ports, not the bitstream's internal behavioral
identity. Packet semantics were inspected in frozen RTL and exercised in
simulation. The hardware manifest records hashes of every RTL and bitstream/XSA.
The configured clock is not evidence of timing closure.

Coordinates use wide signed subtraction and floor division, including negative
boundaries. A pending observation supplies coordinates because RX has none.
Spatial coordinates alone form the key: drones share the same voxel. Metadata
identifies the triggering observation, not voxel ownership. Successful RX replaces
the mirror sum/count; values are cumulative and must never be added again.
Mean is fractional arithmetic `sum/count`, with zero-count protection. It is
not a mean of linear powers. An occupied voxel means sampled RF, not an obstacle
or a collision-safe free-space measurement.

All response fields, lengths, legal flag combinations, slot state, coordinates,
metadata and cumulative transitions are checked before mutation. Capacity
rejection returns slot zero with zero statistics; it never clears occupied slot
zero. Count saturation returns unchanged statistics with rejected+overflow.
The signed sum width can represent every possible signed 32-bit RSSI accumulated
up to the unsigned 32-bit count limit; overflow protection is count saturation.

## Continuous operation and recovery

Input capacity is 32 queued observations, one paired DMA operation in flight.
RX is armed for 32 bytes before TX sends exactly one 28-byte observation.
Concatenating observations into a single MM2S transfer is invalid: only the last
beat receives TLAST and the unpacker discards the overlong packet.

Buffers occupy independent 64-byte aligned/padded areas (two Cortex-A9 cache
lines). CPU builds TX, flushes TX and RX, then transfers ownership to DMA.
Completion requires both IOC and idle, without DMA errors, and exactly 32 RX
bytes. CPU invalidates RX before decoding. Nothing touches/reuses DMA-owned
buffers on failure. Error stop requests DMA reset but never claims to clear PL.
UART work is limited to 64 input and 64 output bytes per loop; output is 16
bounded frames. Slow/disconnected consumers cause counted export drops, not
blocked DMA work. Raw source logs remain the offline authority when PL capacity
or a software queue is exhausted.

Timeouts use elapsed microseconds, not iteration counts. A start failure, DMA
error, bad response or elapsed deadline makes the mirror **unsynchronized**.
Queued observations are dropped and counted; the in-flight observation is
ambiguous. No blind retry: it may already have changed PL statistics. A stopped
mirror remains inspectable but cannot resume. Session mismatches and stale or
duplicate UART sequences do not submit another DMA operation.

There is no exported map reset, snapshot or status register. Software snapshots
read the DDR mirror only, while the queue/DMA are idle, and pause admission while
streaming. They are not independent hardware snapshots. DMA reset, restarting
only the ARM application, or choosing a new host session does not empty PL RAM.
Recovery requires [coordinated FPGA/software restart](BOARD.md). More DDR cannot
expand the fixed 1,024 slots. Future hardware could add a larger lookup,
explicit reset/epoch/status registers, paging or streaming raw observations to
software; none of those facilities exists in this export.

## Host commands

From repository root:

```sh
python3 -m pip install -e ./Mapping/RF_Mapping
python3 -m unittest discover -s Development/Tests/voxel -p 'test_host.py' -v
python3 Development/Tests/voxel/run_suite.py --mode quick --rtl
python3 Development/Tests/voxel/run_suite.py --mode stress --rtl
python3 Development/Tests/voxel/run_suite.py --mode soak --build /tmp/voxel-soak
```

`--rtl` uses the available ModelSim installation's private native compiler loader;
override `--native-runtime` if installed elsewhere. The normal regression is:

```sh
python3 FPGA/modelsim/run_regression.py --native-runtime "$HOME/intelFPGA/20.1"
```

Deterministic synthetic pose/clock replay (no pose hardware claimed):

```sh
rf-voxel bridge-replay Development/Datasets/RF_Mapping/voxel_replay/events.jsonl \
  --config Development/Datasets/RF_Mapping/voxel_replay/alignment.json \
  --raw-log /tmp/pose-raw.jsonl --output /tmp/observations.jsonl
cmp /tmp/observations.jsonl Development/Datasets/RF_Mapping/voxel_replay/observations.jsonl
```

Expected: two observations; the third is rejected as stale. Exact timestamp
precision survives low-word wrap and values above the floating-point exact
integer range. See [measured-pose contract](POSE.md) before live acquisition.

After the board setup and coordinated restart:

```sh
rf-voxel live /tmp/observations.jsonl --port /dev/ttyUSB1 \
  --wire-log /tmp/board.wire --fresh-map
rf-voxel export /tmp/board.wire --output /tmp/board.jsonl
rf-voxel replay /tmp/board.wire --image /tmp/board.png
# In a separate process during acquisition:
rf-voxel replay /tmp/board.wire --follow
```

Port names are examples, not discovered hardware. `--fresh-map` is an operator
attestation that both PL and software were restarted. It is not a clear command.
One capture file is one session. Export keeps exact sum/count, integer timestamps,
physical lower corners in metres, and fractional mean dBm. Sparse rendering builds
six faces per occupied voxel; extreme coordinate separation never allocates a
dense 3D volume. A viewer can be stopped or slowed without delaying acquisition.

The live PC source queue is bounded at 256 records. It drops and counts excess
source arrivals, retaining the raw source file/log. Use `--rate N` to pace replay files at N observations/s. End-of-file acquisition
collects diagnostics, a latency histogram and a quiescent snapshot. Wire writes and reads are
nonblocking, with at most eight pending results. Missing/corrupt responses stop
the session; neither observations nor START are automatically retried.

[Protocol](PROTOCOL.md) · [Board and Vitis setup](BOARD.md) ·
[Research and design choices](SOURCES.md)
