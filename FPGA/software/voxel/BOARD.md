# Vitis 2024.2 and board validation

These are reproducible setup/acceptance instructions, not a claim that the
application has been vendor-compiled or board-tested here. Vitis, Vivado, the ARM
cross compiler and a board are unavailable. The real BSP adapter is host-tested
with mocked vendor calls in both legacy and SDT preprocessor modes.

## Create the application

1. Launch **Vitis Unified IDE 2024.2** in a new workspace. Select **File → New
   Component → Platform**, name `voxel_zybo`, hardware design = the existing
   `FPGA/bitstreams/voxel_readout_with_droneID.xsa`. Select processor
   `ps7_cortexa9_0`, operating system `standalone`, architecture 32-bit and the
   GCC toolchain. Keep the XSA hardware unchanged. Build the platform.
2. In its standalone domain/BSP settings, set stdin and stdout to
   `ps7_uart_1`; retain the generated `axidma`, `uartps`, timer and cache drivers.
   Confirm UART1 is the sole enabled PS UART and canonical `XPAR_XUARTPS_0_*`
   points to it. SDT uses base-address lookup; the legacy branch uses device IDs.
   Confirm `XPAR_XAXIDMA_0_BASEADDR` corresponds to AXI DMA at the HWH's
   `0x40400000`. These are verification values, not hardcoded driver addresses.
3. **File → New Component → Application**, name `voxel_acquire`, platform =
   built `voxel_zybo` XPFM, domain = `standalone_ps7_cortexa9_0`, template =
   **Empty Application**. Add only `voxel_core.c`, `voxel_wire.c`, `voxel_app.c`,
   `zybo_main.c` and their three headers from this directory. Add this directory
   to include paths. Do not add test harnesses or other application mains.
4. Set C standard C11 and application flags `-O2 -g -Wall -Wextra -Werror
   -Wconversion -Wshadow`. Keep BSP's ARM CPU/ABI flags. Do not apply host
   sanitizers to the target or treat the host mock headers as a BSP. No extra
   libraries, SG descriptors, cyclic mode, DMA interrupt wiring or RTOS are used.
5. Open the application's generated `lscript.ld` in its text editor. Map code,
   data, bss, stack and heap to the existing `ps7_ddr_0` memory region. Set stack
   to `0x10000` and heap to `0x1000` (application uses no heap). Inside `SECTIONS`,
   insert `voxel_ddr.ld.inc`. If the generated DDR region has another name,
   use that actual region name in the snippet; do not create guessed addresses.
   `.voxel_ddr` is NOLOAD and `va_init` explicitly clears it on CPU startup.
6. Add linker options `-Wl,-Map=voxel_acquire.map,--cref` and build. Confirm only
   one `main` was linked, all DDR assertions pass, and `.voxel_ddr` includes
   `application` with 64-byte alignment. Inspect the actual ELF symbols using the
   Vitis `arm-none-eabi-nm -S` / `arm-none-eabi-objdump -h` tools. Save ELF, map,
   build transcript, tool version and generated `xparameters.h` with board evidence.
7. Run the map check below with the generated DDR MEMORY region's bounds.
   The HWH currently reports DDR `0x00100000..0x3fffffff`; verify generated BSP
   reservations before using these values. The end argument is exclusive:

```sh
python3 Development/Tests/voxel/check_linker_map.py /path/to/voxel_acquire.map \
  --ddr-start 0x00100000 --ddr-end 0x40000000
```

Expected: aligned nonempty `.voxel_ddr` lies entirely in DDR; no OCM placement.
This check is **pending on an actual Vitis linker map**. Its parser is tested
against valid and invalid synthetic maps; that does not verify target placement.

## Coordinated start

Disconnect producers. Power-cycle or system-reset the Zybo, initialize PS/DDR
using the supplied platform's generated initialization, and program the FPGA
with the existing `voxel_readout_with_droneID.bit` contained in this XSA. Select
that exact bitstream in Vitis's hardware launch configuration; do not regenerate
or substitute an older bitstream. Reload/start `voxel_acquire.elf` from its entry
point. When using an SD boot image, use the generated FSBL, this exact bitstream
and this ELF in that order and verify both PS and PL reset on boot.

Lookup clears 2,048 entries after reset (20.48 us at configured 100 MHz).
Firmware waits a conservative 1 ms after initialization, then accepts START.
There is no software-readable init_done: ready/backpressure still governs the
first DMA transaction. Check the first successful result is `new=1, slot=0,
count=1` on a fresh map. A PS-only debug rerun is not coordinated reset and can
leave map state inconsistent; never attest `--fresh-map` after only restarting
software. A DMA error/timeout requires this whole sequence again. A new random
host session separates logs; the DMA metadata itself contains no epoch token.

## Smoke and stress

Use a verified UART1 USB connection and exclusive access to its device; close
terminal programs. Actual device names are determined on the board PC. Create
the deterministic input using the README's bridge-replay command, then:

```sh
rf-voxel live /tmp/observations.jsonl --port /dev/ttyUSB1 --rate 20 \
  --wire-log /tmp/smoke.wire --fresh-map 2>/tmp/smoke-status.jsonl
rf-voxel export /tmp/smoke.wire --output /tmp/smoke.jsonl
rf-voxel replay /tmp/smoke.wire --image /tmp/smoke.png
```

Expected on a freshly reset map: 2 submitted/completed/accepted, no rejection,
no drops/errors/ambiguous operations; one slot at voxel `[-1,-1,2]`, cumulative
sum `-131`, count `2`, mean `-65.5` dBm. End-of-file live collection requests
STATUS/latency histogram and a quiescent mirror snapshot and records them in the
wire file. No reset command is sent. Capture each run under a unique filename.

For a full-capacity synthetic stress input (retain it as the raw observation log):

```sh
python3 Development/Tests/voxel/board_input.py --count 10000 --seed 1 \
  --output /tmp/board-stress.jsonl
# Coordinate a fresh FPGA/software restart before this separate session.
rf-voxel live /tmp/board-stress.jsonl --port /dev/ttyUSB1 --rate 50 \
  --wire-log /tmp/stress.wire --fresh-map 2>/tmp/stress-status.jsonl
rf-voxel export /tmp/stress.wire --output /tmp/stress.jsonl
```

Expected if no source/queue/export drops: 10,000 completed, 6,410 accepted,
3,590 capacity rejections, 1,024 occupied slots. Subsequent existing-key updates
still succeed. Unknown-key rejection must not change slot zero. Coordinate a
new hardware/software restart between independent sessions. Keep all rejected
raw observations for offline mapping; DDR does not add hardware slots.

Repeat runs at increasing source rates (20, 50, 80, 100, 150 observations/s),
measuring wall time, submitted/completed counts, source and firmware drops,
export drops, histogram/maximum/mean DMA latency and output byte count. The
log2 histogram gives bounded latency distributions, not exact percentiles.
Use ILA if available to separate PL clocks from CPU/cache/poll latency; record
instrumentation overhead. Plot in another process, suspend it and confirm
acquisition counters are unchanged. Disconnect UART during an active transfer,
then preserve the partial capture and perform coordinated restart; do not retry
missing measurements. Verify corrupt-frame, busy-snapshot, queue-full and wrong-
session handling with the documented frame API under controlled tests.

At 115200 8N1, each direction carries at most 11,520 bytes/s. One unescaped ACK
plus result costs 30+78=108 output bytes, giving an ideal upper bound of about
106 observations/s before escaping, diagnostics and software delays. This is a
transport calculation, not a board throughput measurement. Host, RTL and board
measurements must remain separately labelled. LUT/FF/BRAM/DSP utilization and
100 MHz timing closure require implementation reports or a later Vivado run;
no such reports were found in this repository.
