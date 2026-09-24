/*
Author: Sanat Konda
Updated: Sept 24, 2026

Purpose: Expose the sparse voxel lookup module in Vivado's block design.
The wrapper preserves the signed coordinate and valid/ready interfaces.
*/

module voxel_lookup_wrapper #(
    parameter integer MAX_VOXELS = 1024,
    parameter integer TABLE_SIZE = 2048
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET aresetn" *)
    input wire aclk,

    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,

    input  wire signed [32:0] voxel_x,
    input  wire signed [32:0] voxel_y,
    input  wire signed [32:0] voxel_z,
    input  wire signed [31:0] voxel_rssi_dbm,
    input  wire               voxel_valid,
    output wire               voxel_ready,

    output wire [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] lookup_slot,
    output wire signed [31:0] lookup_rssi_dbm,
    output wire               lookup_new,
    output wire               lookup_rejected,
    output wire               lookup_valid,
    input  wire               lookup_ready,

    output wire               init_done,
    output wire               map_full,
    output wire [$clog2(MAX_VOXELS+1)-1:0] used_voxels
);

    voxel_lookup #(
        .MAX_VOXELS(MAX_VOXELS),
        .TABLE_SIZE(TABLE_SIZE)
    ) voxel_lookup_inst (
        .aclk(aclk),
        .aresetn(aresetn),
        .voxel_x(voxel_x),
        .voxel_y(voxel_y),
        .voxel_z(voxel_z),
        .voxel_rssi_dbm(voxel_rssi_dbm),
        .voxel_valid(voxel_valid),
        .voxel_ready(voxel_ready),
        .lookup_slot(lookup_slot),
        .lookup_rssi_dbm(lookup_rssi_dbm),
        .lookup_new(lookup_new),
        .lookup_rejected(lookup_rejected),
        .lookup_valid(lookup_valid),
        .lookup_ready(lookup_ready),
        .init_done(init_done),
        .map_full(map_full),
        .used_voxels(used_voxels)
    );

endmodule
