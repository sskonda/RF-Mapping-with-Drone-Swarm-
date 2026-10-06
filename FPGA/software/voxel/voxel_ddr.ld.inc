/* Insert INSIDE SECTIONS in the application's generated lscript.ld.
   Use its existing ps7_ddr_0 MEMORY region; never invent a physical address. */
.voxel_ddr (NOLOAD) : ALIGN(64)
{
    __voxel_ddr_start = .;
    KEEP(*(.voxel_ddr))
    . = ALIGN(64);
    __voxel_ddr_end = .;
} > ps7_ddr_0
ASSERT(__voxel_ddr_start >= ORIGIN(ps7_ddr_0), "voxel mirror outside DDR")
ASSERT(__voxel_ddr_end <= ORIGIN(ps7_ddr_0) + LENGTH(ps7_ddr_0), "voxel mirror exceeds DDR")
ASSERT((__voxel_ddr_start % 64) == 0, "voxel DMA buffers misaligned")
