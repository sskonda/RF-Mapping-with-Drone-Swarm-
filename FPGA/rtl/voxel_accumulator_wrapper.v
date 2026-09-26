/*
Author: Sanat Konda
Updated: Sept 25, 2026

Purpose: Expose the voxel RSSI accumulator in Vivado's block design.
The wrapper preserves the slot, signed sum, count, and valid/ready interfaces.
*/

module voxel_accumulator_wrapper #(
    parameter integer MAX_VOXELS = 1024,
    parameter integer COUNT_WIDTH = 32
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET aresetn" *)
    input wire aclk,

    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,

    input  wire [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] lookup_slot,
    input  wire signed [31:0] lookup_rssi_dbm,
    input  wire lookup_new,
    input  wire lookup_rejected,
    input  wire lookup_valid,
    output wire lookup_ready,

    output wire [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] acc_slot,
    output wire signed [COUNT_WIDTH+31:0] acc_rssi_sum,
    output wire [COUNT_WIDTH-1:0] acc_count,
    output wire acc_new,
    output wire acc_rejected,
    output wire acc_overflow,
    output wire acc_valid,
    input  wire acc_ready
);

    voxel_accumulator #(
        .MAX_VOXELS(MAX_VOXELS),
        .COUNT_WIDTH(COUNT_WIDTH)
    ) voxel_accumulator_inst (
        .aclk(aclk),
        .aresetn(aresetn),
        .lookup_slot(lookup_slot),
        .lookup_rssi_dbm(lookup_rssi_dbm),
        .lookup_new(lookup_new),
        .lookup_rejected(lookup_rejected),
        .lookup_valid(lookup_valid),
        .lookup_ready(lookup_ready),
        .acc_slot(acc_slot),
        .acc_rssi_sum(acc_rssi_sum),
        .acc_count(acc_count),
        .acc_new(acc_new),
        .acc_rejected(acc_rejected),
        .acc_overflow(acc_overflow),
        .acc_valid(acc_valid),
        .acc_ready(acc_ready)
    );

endmodule
