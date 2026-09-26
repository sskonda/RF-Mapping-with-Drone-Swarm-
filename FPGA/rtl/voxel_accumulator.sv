/*
Author: Sanat Konda
Updated: Sept 25, 2026

Purpose: Accumulate RSSI sums and observation counts by sparse voxel slot.
Synchronous BRAM updates use valid/ready flow control and initialize on lookup_new.
*/

module voxel_accumulator #(
    parameter int MAX_VOXELS = 1024,
    parameter int COUNT_WIDTH = 32
) (
    input  logic               aclk,
    input  logic               aresetn,

    input  logic [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] lookup_slot,
    input  logic signed [31:0] lookup_rssi_dbm,
    input  logic               lookup_new,
    input  logic               lookup_rejected,
    input  logic               lookup_valid,
    output logic               lookup_ready,

    output logic [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] acc_slot,
    output logic signed [COUNT_WIDTH+31:0] acc_rssi_sum,
    output logic [COUNT_WIDTH-1:0] acc_count,
    output logic               acc_new,
    output logic               acc_rejected,
    output logic               acc_overflow,
    output logic               acc_valid,
    input  logic               acc_ready
);

    localparam int SUM_WIDTH = 32 + COUNT_WIDTH;

    typedef struct packed {
        logic signed [SUM_WIDTH-1:0] sum;
        logic [COUNT_WIDTH-1:0]      count;
    } stats_t;

    (* ram_style = "block" *) stats_t stats_mem [MAX_VOXELS];
    stats_t read_stats, next_stats;
    logic pending, pending_rejected;
    logic signed [31:0] pending_rssi;
    logic accept, invalid_slot, count_full, write_enable;

    assign lookup_ready = aresetn && !pending && (!acc_valid || acc_ready);
    assign accept = lookup_valid && lookup_ready;
    assign invalid_slot = (32'(lookup_slot) >= MAX_VOXELS);
    assign count_full = !acc_new && (&read_stats.count);
    assign write_enable = aresetn && pending && !pending_rejected && !count_full;

    // A new slot ignores stale RAM. Reset this block and the lookup together.
    always_comb begin
        next_stats = '0;
        if (!pending_rejected) begin
            if (acc_new) begin
                next_stats.sum = SUM_WIDTH'(pending_rssi);
                next_stats.count = COUNT_WIDTH'(1);
            end else begin
                next_stats = read_stats;
                if (!count_full) begin
                    next_stats.sum = read_stats.sum + SUM_WIDTH'(pending_rssi);
                    next_stats.count = read_stats.count + 1'b1;
                end
            end
        end
    end

    // Read and write occur on alternate cycles, including repeated same-slot updates.
    always_ff @(posedge aclk) begin
        if (write_enable)
            stats_mem[acc_slot] <= next_stats;
        if (accept && !lookup_rejected && !invalid_slot && !lookup_new)
            read_stats <= stats_mem[lookup_slot];
    end

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            pending <= 1'b0;
            acc_valid <= 1'b0;
        end else begin
            if (acc_ready)
                acc_valid <= 1'b0;
            if (accept) begin
                pending <= 1'b1;
            end else if (pending) begin
                pending <= 1'b0;
                acc_valid <= 1'b1;
            end
        end

        // Reset only control bits. Payload is meaningful while acc_valid is high.
        if (accept) begin
            acc_slot <= lookup_slot;
            acc_new <= lookup_new;
            pending_rssi <= lookup_rssi_dbm;
            pending_rejected <= lookup_rejected || invalid_slot;
        end
        if (pending) begin
            acc_rssi_sum <= next_stats.sum;
            acc_count <= next_stats.count;
            acc_rejected <= pending_rejected || count_full;
            acc_overflow <= !pending_rejected && count_full;
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
