# Firmware selection

The continuous UART acquisition application is in [`../software/voxel`](../software/voxel/README.md).
Build **one main per application**.

`main_voxel_dma_droneID_readout_test.c` remains the working, manually operated
seven-word/eight-word smoke-test reference for `voxel_readout_with_droneID.xsa`.
It requires a fresh hardware map and synthetic timestamps; it is not continuous acquisition.

`main_voxel_dma_readout_test.c` and `main_voxel_accumulator_test.c` are **legacy**,
incompatible protocol/hardware examples. Do not link them into the current app
or run them against the current metadata bitstream. Their source is retained
for historical experiments.
