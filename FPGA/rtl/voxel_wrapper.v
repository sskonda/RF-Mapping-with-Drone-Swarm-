/*
Author: Sanat Konda
Updated: Oct 5, 2026

Purpose: Expose the observation interface in Vivado with source metadata.
*/

module voxel_wrapper #(
    parameter integer X_ORIGIN_MM = 0,
    parameter integer Y_ORIGIN_MM = 0,
    parameter integer Z_ORIGIN_MM = 0,
    parameter integer VOXEL_SIZE_MM = 500
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET aresetn" *)
    input wire aclk,

    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,

    input  wire signed [31:0] x_mm,
    input  wire signed [31:0] y_mm,
    input  wire signed [31:0] z_mm,
    input  wire signed [31:0] rssi_dbm,
    input wire [31:0] observation_drone_id,
    input wire [63:0] observation_timestamp_us,
    input  wire               observation_valid,
    output wire               observation_ready,

    output wire signed [32:0] voxel_x,
    output wire signed [32:0] voxel_y,
    output wire signed [32:0] voxel_z,
    output wire signed [31:0] voxel_rssi_dbm,
    output wire [31:0] voxel_drone_id,
    output wire [63:0] voxel_timestamp_us,
    output wire               voxel_valid,
    input  wire               voxel_ready
);

    voxel #(
        .X_ORIGIN_MM(X_ORIGIN_MM),
        .Y_ORIGIN_MM(Y_ORIGIN_MM),
        .Z_ORIGIN_MM(Z_ORIGIN_MM),
        .VOXEL_SIZE_MM(VOXEL_SIZE_MM)
    ) voxel_inst (
        .aclk(aclk),
        .aresetn(aresetn),
        .x_mm(x_mm),
        .y_mm(y_mm),
        .z_mm(z_mm),
        .rssi_dbm(rssi_dbm),
        .observation_drone_id(observation_drone_id),
        .observation_timestamp_us(observation_timestamp_us),
        .observation_valid(observation_valid),
        .observation_ready(observation_ready),
        .voxel_x(voxel_x),
        .voxel_y(voxel_y),
        .voxel_z(voxel_z),
        .voxel_rssi_dbm(voxel_rssi_dbm),
        .voxel_drone_id(voxel_drone_id),
        .voxel_timestamp_us(voxel_timestamp_us),
        .voxel_valid(voxel_valid),
        .voxel_ready(voxel_ready)
    );

endmodule
