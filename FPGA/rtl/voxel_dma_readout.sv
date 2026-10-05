/*
Author: Sanat Konda
Updated: Oct 5, 2026

Purpose: Return accumulator results as eight-word AXI4-Stream packets.
Each packet contains slot, sum, count, flags, drone ID, and acquisition time.
*/

module voxel_dma_readout #(
    parameter int MAX_VOXELS = 1024,
    parameter int COUNT_WIDTH = 32
) (
    input  logic aclk,
    input  logic aresetn,

    input  logic [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] acc_slot,
    input  logic signed [COUNT_WIDTH+31:0] acc_rssi_sum,
    input  logic [COUNT_WIDTH-1:0] acc_count,
    input  logic acc_new,
    input  logic acc_rejected,
    input  logic acc_overflow,
    input logic [31:0] acc_drone_id,
    input logic [63:0] acc_timestamp_us,
    input  logic acc_valid,
    output logic acc_ready,

    output logic [31:0] m_axis_tdata,
    output logic [3:0] m_axis_tkeep,
    output logic m_axis_tvalid,
    input  logic m_axis_tready,
    output logic m_axis_tlast
);

    logic [31:0] drone_q;
    logic [63:0] timestamp_q;
    logic busy;
    logic [2:0] word_index, flags_q;
    logic [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] slot_q;
    logic signed [COUNT_WIDTH+31:0] sum_q;
    logic [COUNT_WIDTH-1:0] count_q;
    logic signed [63:0] sum_extended;
    logic accept, transfer, last_word;

    assign last_word = (word_index == 3'd7);
    assign acc_ready = aresetn && (!busy || (last_word && m_axis_tready));
    assign accept = acc_valid && acc_ready;
    assign m_axis_tvalid = aresetn && busy;
    assign m_axis_tkeep = 4'b1111;
    assign m_axis_tlast = busy && last_word;
    assign transfer = m_axis_tvalid && m_axis_tready;
    assign sum_extended = 64'(sum_q);

    always_comb begin
        case (word_index)
            3'd0: m_axis_tdata = 32'(slot_q);
            3'd1: m_axis_tdata = sum_extended[31:0];
            3'd2: m_axis_tdata = sum_extended[63:32];
            3'd3: m_axis_tdata = 32'(count_q);
            3'd4: m_axis_tdata = {29'b0, flags_q};
            3'd5: m_axis_tdata = drone_q;
            3'd6: m_axis_tdata = timestamp_q[31:0];
            3'd7: m_axis_tdata = timestamp_q[63:32];
            default: m_axis_tdata = '0;
        endcase
    end

    always_ff @(posedge aclk) begin
        if (!aresetn)
            busy <= 1'b0;
        else if (accept)
            busy <= 1'b1;
        else if (transfer && last_word)
            busy <= 1'b0;

        // A new result may replace the old one on its final transferred word.
        if (accept) begin
            slot_q <= acc_slot;
            drone_q <= acc_drone_id;
            timestamp_q <= acc_timestamp_us;
            sum_q <= acc_rssi_sum;
            count_q <= acc_count;
            flags_q <= {acc_overflow, acc_rejected, acc_new};
            word_index <= '0;
        end else if (transfer && !last_word) begin
            word_index <= word_index + 1'b1;
        end
    end

    // synthesis translate_off
    initial begin
        if (MAX_VOXELS < 1)
            $fatal(1, "MAX_VOXELS must be positive");
        if (COUNT_WIDTH < 1 || COUNT_WIDTH > 32)
            $fatal(1, "COUNT_WIDTH must be between 1 and 32");
    end
    // synthesis translate_on

endmodule
