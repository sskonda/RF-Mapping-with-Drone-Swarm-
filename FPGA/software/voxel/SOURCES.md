# Sources consulted and choices

Research was targeted before implementation; source versions are pinned where
possible. Project baseline reviewed: `4dfa3979b28f42e21d32ce269452b24917a0f2b4`.
The workspace HEAD matched it at start. Current HWH, all six RTL modules and
wrappers, the working drone-ID firmware, the ESP32 RSSI sketch, existing
RF_Mapping package/dependencies and repository CONTRIBUTING instructions were
inspected. No applicable AGENTS.md was found. No supplied implementation reports
were found. Historical screenshot/PASS claims were not used as fresh evidence.

- [AMD PG021, Direct Register Mode](https://docs.amd.com/r/en-US/pg021_axi_dma/Direct-Register-Mode-Simple-DMA):
  simple-mode start/completion semantics, alignment without DRE, and S2MM length
  constraints. These support one RX-first paired transfer per observation.
  The accessible PG021 page is revision 7.1 dated 2025-06-24; the driver below is
  specifically the requested Vitis release.
- [AXI DMA simple polling example, xilinx_v2024.2](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2024.2/XilinxProcessorIPLib/drivers/axidma/examples/xaxidma_example_simple_poll.c)
  and [driver implementation](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2024.2/XilinxProcessorIPLib/drivers/axidma/src/xaxidma.c):
  BSP config lookup branches, cache maintenance, interrupt disabling and simple
  transfer API. The new adapter adds elapsed deadlines, status/length validation
  and a nonblocking service loop rather than copying the blocking example.
- [UARTPS registers, xilinx_v2024.2](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2024.2/XilinxProcessorIPLib/drivers/uartps/src/xuartps_hw.h)
  and [lookup implementation](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2024.2/XilinxProcessorIPLib/drivers/uartps/src/xuartps_sinit.c):
  FIFO polling, UART fault bits and SDT address lookup for bounded UART work.
- [Greg Stitt / ARC Lab SystemVerilog tutorial](https://github.com/ARC-Lab-UF/sv-tutorial),
  [Crafting Clean Reset Logic](https://stitt-hub.com/crafting-clean-reset-logic/),
  and [Race Conditions: The Root of All Verilog Evil](https://stitt-hub.com/race-conditions-the-root-of-all-verilog-evil/):
  testbench drive/sample discipline, independent scoreboards, control reset and
  validity-gated payload checks. Stimulus drives falling edges; scoreboards
  inspect rising-edge pre-NBA handshakes. No force initialization hides X values.
- [Matplotlib Poly3DCollection](https://matplotlib.org/stable/api/_as_gen/mpl_toolkits.mplot3d.art3d.Poly3DCollection.html):
  collections of planar faces support sparse cubes using the existing plotting
  dependency. Work scales with occupied slots instead of spatial extent.
- [Vitis UG1400 2024.2](https://docs.amd.com/r/2024.2-English/ug1400-vitis-embedded)
  and [Modifying a Linker Script](https://docs.amd.com/r/2024.2-English/ug1400-vitis-embedded/Modifying-a-Linker-Script):
  platform/application/domain workflow and generated linker-script editing.
  Setup is documented for later vendor validation, not presented as an executed build.

No research source is used to claim measured pose, clock synchronization, board
performance, RF obstacle occupancy or timing closure that was not measured.
