# FPGA

FPGA work has its own subsystem: architecture, RTL for RF/vision processing,
filtering and accelerators, interfaces, verification/testbenches, constraints,
implementation scripts, and release bitstreams.

The current RTL implements AXI stream incrementing, RF packet unpacking, signed
voxel conversion, sparse voxel lookup, and RSSI accumulation. Sources and Vivado
wrappers are in [rtl](rtl/), with self-checking SystemVerilog tests in [tb](tb/).
Exported hardware platforms are in [bitstreams](bitstreams/), and processing-system
test code is in [vitis_code](vitis_code/).

The [ModelSim project and regression instructions](modelsim/README.md) cover every
RTL `.sv` file. The recorded regression passes all seven testbenches; see the
[verification report](modelsim/VERIFICATION.md) and
[labeled waveform screenshots](waveform_screenshots/README.md).

Physical board schematics belong in [Hardware](../Hardware/); FPGA runtime and
implementation sources remain here.

Current continuous software: [UART voxel acquisition](software/voxel/README.md).
Current fresh verification: [results](../Development/Reports/voxel/RESULTS.md).
