/*
Author: Sanat Konda
Updated: Oct 4, 2026

Purpose: Verify result packet serialization, signed extension, and flow control.
Check each word, TKEEP, TLAST, stalls, packet replacement, and partial-packet reset.
*/

`timescale 1ns/1ps

module readout_case #(
    parameter int MAX_VOXELS = 1024,
    parameter int COUNT_WIDTH = 32
) (output bit done);
    localparam int SLOT_WIDTH = MAX_VOXELS > 1 ? $clog2(MAX_VOXELS) : 1;
    localparam int SUM_WIDTH = 32 + COUNT_WIDTH;
    bit aclk = 0;
    always #5 aclk = ~aclk;
    logic aresetn = 0;
    logic [SLOT_WIDTH-1:0] acc_slot = 0;
    logic signed [SUM_WIDTH-1:0] acc_rssi_sum = 0;
    logic [COUNT_WIDTH-1:0] acc_count = 0;
    logic acc_new = 0, acc_rejected = 0, acc_overflow = 0, acc_valid = 0;
    wire acc_ready;
    wire [31:0] m_axis_tdata;
    wire [3:0] m_axis_tkeep;
    wire m_axis_tvalid, m_axis_tlast;
    logic m_axis_tready = 0;
    int ready_mode = 0;
    logic [31:0] expected[$], wanted;
    logic [36:0] held_payload;
    bit held = 0, check_burst = 0;
    int cycle = 0, last_burst_cycle = 0, burst_accepted = 0;
    int accepted = 0, packets = 0, words = 0, aborted = 0, position = 0, stalls = 0;

    voxel_dma_readout #(.MAX_VOXELS(MAX_VOXELS), .COUNT_WIDTH(COUNT_WIDTH)) dut (
        .aclk, .aresetn, .acc_slot, .acc_rssi_sum, .acc_count,
        .acc_new, .acc_rejected, .acc_overflow, .acc_valid, .acc_ready,
        .m_axis_tdata, .m_axis_tkeep, .m_axis_tvalid, .m_axis_tready, .m_axis_tlast
    );

    always @(negedge aclk) begin
        case (ready_mode)
            0: m_axis_tready = 1;
            1: m_axis_tready = ($urandom_range(0, 3) != 0);
            default: m_axis_tready = 0;
        endcase
    end

    always @(posedge aclk) begin : scoreboard
        longint signed sum_value;
        cycle++;
        if (!aresetn) begin
            if (expected.size() != 0) aborted++;
            expected.delete();
            position = 0;
            held = 0;
        end else begin
            if (held && (!m_axis_tvalid ||
                {m_axis_tlast, m_axis_tkeep, m_axis_tdata} !== held_payload))
                $fatal(1, "Stream changed while stalled");
            held = m_axis_tvalid && !m_axis_tready;
            held_payload = {m_axis_tlast, m_axis_tkeep, m_axis_tdata};
            if (held) stalls++;
            if (acc_valid && acc_ready) begin
                if (check_burst) begin
                    if (burst_accepted != 0 && cycle - last_burst_cycle != 5)
                        $fatal(1, "Continuous results did not accept every five clocks");
                    last_burst_cycle = cycle;
                    burst_accepted++;
                end
                sum_value = longint'(acc_rssi_sum);
                expected.push_back(32'(acc_slot));
                expected.push_back(32'(sum_value));
                expected.push_back(32'(sum_value >>> 32));
                expected.push_back(32'(acc_count));
                expected.push_back(32'(acc_new) | (32'(acc_rejected) << 1) |
                                   (32'(acc_overflow) << 2));
                accepted++;
            end
            if (m_axis_tvalid && m_axis_tready) begin
                if (expected.size() == 0) $fatal(1, "Unexpected output word");
                wanted = expected.pop_front();
                if (m_axis_tdata !== wanted || m_axis_tkeep !== 4'hf ||
                    m_axis_tlast !== (position == 4))
                    $fatal(1, "Packet word mismatch at position %0d", position);
                words++;
                if (position == 4) begin
                    packets++;
                    position = 0;
                end else position++;
            end
        end
    end

    task automatic send(input int slot, input longint signed sum,
                        input int unsigned count, input logic [2:0] flags);
        @(negedge aclk);
        acc_slot = SLOT_WIDTH'(slot);
        acc_rssi_sum = SUM_WIDTH'(sum);
        acc_count = COUNT_WIDTH'(count);
        {acc_overflow, acc_rejected, acc_new} = flags;
        acc_valid = 1;
        do @(posedge aclk); while (!acc_ready);
        @(negedge aclk);
        acc_valid = 0;
    endtask

    task automatic drain;
        wait (expected.size() == 0);
        repeat (3) @(negedge aclk);
    endtask

    task automatic reset_all;
        @(negedge aclk);
        aresetn = 0;
        acc_valid = 0;
        repeat (3) @(negedge aclk);
        aresetn = 1;
    endtask

    initial begin : stimulus
        int start_words;
        reset_all();
        send(0, -63, 1, 3'b001);
        send(MAX_VOXELS-1, -130, 2, 0);
        send(0, -64'sh8000000000000000, 32'hffffffff, 3'b110);
        send(0, 64'sh7fffffffffffffff, 32'hffffffff, 0);
        send(0, 0, 0, 3'b010);
        drain();

        // Hold the final word: TLAST, flags, and valid must remain stable.
        ready_mode = 0;
        start_words = words;
        send(0, -193, 3, 0);
        wait (words == start_words + 4);
        ready_mode = 2;
        repeat (20) @(negedge aclk);
        ready_mode = 0;
        drain();

        // Reset after 0 through 4 transferred words; discard the partial packet.
        for (int partial = 0; partial < 5; partial++) begin
            ready_mode = 2;
            repeat (2) @(negedge aclk);
            start_words = words;
            send(0, -99, 1, 1);
            if (partial != 0) begin
                ready_mode = 0;
                wait (words == start_words + partial);
            end
            reset_all();
            ready_mode = 0;
            send(0, -7, 1, 1);
            drain();
        end

        ready_mode = 1;
        for (int i = 0; i < 300; i++)
            send(int'($urandom_range(0, MAX_VOXELS-1)),
                 64'({$urandom(), $urandom()}), $urandom(), 3'($urandom()));
        drain();
        ready_mode = 0;
        repeat (2) @(negedge aclk);
        check_burst = 1;
        for (int i = 0; i < 20; i++) send(0, -64'sd63-longint'(i), i+1, 0);
        check_burst = 0;
        drain();
        if (accepted != packets + aborted || aborted != 5 ||
            burst_accepted != 20 || stalls == 0)
            $fatal(1, "Readout coverage/accounting failure");
        $display("PASS readout MAX=%0d COUNT=%0d: packets=%0d reset_aborts=%0d stalls=%0d",
                 MAX_VOXELS, COUNT_WIDTH, packets, aborted, stalls);
        done = 1;
    end
endmodule

module tb_voxel_dma_readout;
    wire [2:0] done;
    readout_case #(.MAX_VOXELS(1024), .COUNT_WIDTH(32)) normal(done[0]);
    readout_case #(.MAX_VOXELS(5), .COUNT_WIDTH(3)) narrow(done[1]);
    readout_case #(.MAX_VOXELS(1), .COUNT_WIDTH(1)) single_slot(done[2]);
    initial begin
        wait (&done);
        $display("PASS all readout configurations");
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "Readout test timed out");
    end
endmodule
