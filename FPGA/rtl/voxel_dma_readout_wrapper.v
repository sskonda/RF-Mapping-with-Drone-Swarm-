/*
Author: Sanat Konda
Updated: Oct 4, 2026

Purpose: Connect the accumulator readout to the existing AXI DMA receive path.
S_AXIS drains the unpacker's original echo; M_AXIS returns accumulator results.
*/

module voxel_dma_readout_wrapper #(
    parameter integer MAX_VOXELS = 1024,
    parameter integer COUNT_WIDTH = 32
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXIS:M_AXIS, ASSOCIATED_RESET aresetn" *)
    input wire aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input wire aresetn,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *)
    input wire [31:0] s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *)
    input wire s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *)
    output wire s_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *)
    input wire s_axis_tlast,

    input wire [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] acc_slot,
    input wire signed [COUNT_WIDTH+31:0] acc_rssi_sum,
    input wire [COUNT_WIDTH-1:0] acc_count,
    input wire acc_new,
    input wire acc_rejected,
    input wire acc_overflow,
    input wire acc_valid,
    output wire acc_ready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output wire [31:0] m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output wire [3:0] m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output wire m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input wire m_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
    output wire m_axis_tlast
);

    // The unpacker already extracts observations. Only its echo is discarded.
    // The three S_AXIS input payload/control pins are intentionally unused.
    assign s_axis_tready = aresetn;

    voxel_dma_readout #(
        .MAX_VOXELS(MAX_VOXELS),
        .COUNT_WIDTH(COUNT_WIDTH)
    ) voxel_dma_readout_inst (
        .aclk(aclk),
        .aresetn(aresetn),
        .acc_slot(acc_slot),
        .acc_rssi_sum(acc_rssi_sum),
        .acc_count(acc_count),
        .acc_new(acc_new),
        .acc_rejected(acc_rejected),
        .acc_overflow(acc_overflow),
        .acc_valid(acc_valid),
        .acc_ready(acc_ready),
        .m_axis_tdata(m_axis_tdata),
        .m_axis_tkeep(m_axis_tkeep),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),
        .m_axis_tlast(m_axis_tlast)
    );

endmodule
