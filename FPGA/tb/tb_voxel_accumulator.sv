/*
Author: Sanat Konda
Updated: Sept 25, 2026

Purpose: Verify voxel RSSI accumulation against an independent sum/count model.
Tests repeated slots, signed limits, backpressure, rejection, overflow, and reset.
*/

`timescale 1ns/1ps

module accumulator_case #(
    parameter int MAX_VOXELS = 5,
    parameter int COUNT_WIDTH = 3
) (output bit done);
    localparam int SLOT_WIDTH = MAX_VOXELS > 1 ? $clog2(MAX_VOXELS) : 1;
    localparam int SUM_WIDTH = 32 + COUNT_WIDTH;
    localparam int PAYLOAD_WIDTH = SLOT_WIDTH + SUM_WIDTH + COUNT_WIDTH + 3;
    localparam longint unsigned COUNT_LIMIT = (64'd1 << COUNT_WIDTH) - 1;

    bit aclk = 0;
    always #5 aclk = ~aclk;
    logic aresetn = 0;
    logic [SLOT_WIDTH-1:0] lookup_slot = '0;
    logic signed [31:0] lookup_rssi_dbm = 0;
    logic lookup_new = 0, lookup_rejected = 0, lookup_valid = 0;
    wire lookup_ready;
    wire [SLOT_WIDTH-1:0] acc_slot;
    wire signed [SUM_WIDTH-1:0] acc_rssi_sum;
    wire [COUNT_WIDTH-1:0] acc_count;
    wire acc_new, acc_rejected, acc_overflow, acc_valid;
    logic acc_ready = 1;
    int ready_mode = 0;

    voxel_accumulator_wrapper #(.MAX_VOXELS(MAX_VOXELS), .COUNT_WIDTH(COUNT_WIDTH)) dut (
        .aclk, .aresetn, .lookup_slot, .lookup_rssi_dbm, .lookup_new,
        .lookup_rejected, .lookup_valid, .lookup_ready, .acc_slot,
        .acc_rssi_sum, .acc_count, .acc_new, .acc_rejected,
        .acc_overflow, .acc_valid, .acc_ready
    );

    typedef struct packed {
        logic [SLOT_WIDTH-1:0] slot;
        longint signed sum;
        longint unsigned count;
        bit is_new, rejected, overflow;
    } result_t;
    result_t expected[$], result;
    longint signed sums [MAX_VOXELS];
    longint unsigned counts [MAX_VOXELS];
    bit seen [MAX_VOXELS];
    logic [PAYLOAD_WIDTH-1:0] held_payload;
    wire [PAYLOAD_WIDTH-1:0] payload =
        {acc_slot, acc_rssi_sum, acc_count, acc_new, acc_rejected, acc_overflow};
    bit held = 0;
    int accepted = 0, received = 0, aborted = 0, stalled_cycles = 0;
    int rejected_results = 0, overflow_results = 0;
    bit check_burst = 0;
    int cycle = 0, last_burst_cycle = 0, burst_accepted = 0;

    always @(negedge aclk) begin
        case (ready_mode)
            0: acc_ready = 1;
            1: acc_ready = ($urandom_range(0, 3) != 0);
            default: acc_ready = 0;
        endcase
    end

    always @(posedge aclk) begin
        cycle++;
        if (!aresetn) begin
            aborted += expected.size();
            expected.delete();
            held = 0;
            foreach (seen[i]) begin
                seen[i] = 0;
                sums[i] = 0;
                counts[i] = 0;
            end
        end else begin
            if (held && (!acc_valid || payload !== held_payload))
                $fatal(1, "Output changed under backpressure");
            held = acc_valid && !acc_ready;
            held_payload = payload;
            if (held) stalled_cycles++;

            if (lookup_valid && lookup_ready) begin
                if (check_burst) begin
                    if (burst_accepted != 0 && cycle - last_burst_cycle != 2)
                        $fatal(1, "Burst handshakes were %0d cycles apart",
                               cycle - last_burst_cycle);
                    last_burst_cycle = cycle;
                    burst_accepted++;
                end
                result = '0;
                result.slot = lookup_slot;
                result.is_new = lookup_new;
                result.rejected = lookup_rejected || (int'(lookup_slot) >= MAX_VOXELS);
                if (!result.rejected) begin
                    if (lookup_new) begin
                        sums[lookup_slot] = longint'(lookup_rssi_dbm);
                        counts[lookup_slot] = 1;
                        seen[lookup_slot] = 1;
                    end else begin
                        if (!seen[lookup_slot]) $fatal(1, "Test used an uninitialized slot");
                        if (counts[lookup_slot] == COUNT_LIMIT) begin
                            result.rejected = 1;
                            result.overflow = 1;
                        end else begin
                            sums[lookup_slot] += longint'(lookup_rssi_dbm);
                            counts[lookup_slot]++;
                        end
                    end
                    result.sum = sums[lookup_slot];
                    result.count = counts[lookup_slot];
                end
                expected.push_back(result);
                accepted++;
            end

            if (acc_valid && acc_ready) begin
                if (expected.size() == 0) $fatal(1, "Unexpected output");
                result = expected.pop_front();
                if (acc_slot !== result.slot ||
                    longint'(acc_rssi_sum) !== result.sum ||
                    64'(acc_count) !== result.count ||
                    acc_new !== result.is_new || acc_rejected !== result.rejected ||
                    acc_overflow !== result.overflow)
                    $fatal(1, "MAX=%0d COUNT=%0d response %0d mismatch: sum=%0d/%0d count=%0d/%0d",
                           MAX_VOXELS, COUNT_WIDTH, received,
                           acc_rssi_sum, result.sum, acc_count, result.count);
                received++;
                if (acc_rejected) rejected_results++;
                if (acc_overflow) overflow_results++;
            end
        end
    end

    task automatic send(input int slot, input int signed rssi,
                        input bit is_new = 0, input bit rejected = 0);
        @(negedge aclk);
        lookup_slot = SLOT_WIDTH'(slot);
        lookup_rssi_dbm = rssi;
        lookup_new = is_new;
        lookup_rejected = rejected;
        lookup_valid = 1;
        do @(posedge aclk); while (!lookup_ready);
        @(negedge aclk);
        lookup_valid = 0;
    endtask

    task automatic drain;
        wait (expected.size() == 0);
        repeat (3) @(negedge aclk);
    endtask

    task automatic reset_all;
        @(negedge aclk);
        aresetn = 0;
        lookup_valid = 0;
        repeat (3) @(negedge aclk);
        aresetn = 1;
    endtask

    initial begin : stimulus
        int slot, base_received;
        reset_all();
        send(0, -63, 1);
        send(0, -67);
        send(0, -2147483648);
        send(0, 2147483647);
        send(0, 0, 0, 1);
        if ((1 << SLOT_WIDTH) > MAX_VOXELS)
            send(MAX_VOXELS, -99, 1);

        if (COUNT_WIDTH <= 4) begin
            while (counts[0] < COUNT_LIMIT) send(0, -2147483648);
            send(0, 2147483647);
            send(0, -1);
            send(0, 2147483647, 1);
            while (counts[0] < COUNT_LIMIT) send(0, 2147483647);
            send(0, -2147483648);
        end
        drain();

        // A held response must not cause duplicate updates.
        ready_mode = 2;
        send(0, -63, 1);
        wait (acc_valid);
        repeat (25) @(negedge aclk);
        ready_mode = 0;
        drain();
        send(0, -67);
        drain();

        // Reset with an unconsumed response, then reuse the same RAM slot.
        ready_mode = 2;
        send(0, -10);
        wait (acc_valid);
        reset_all();
        ready_mode = 0;
        send(0, -7, 1);
        drain();

        // Reset between acceptance and writeback.
        send(0, -90);
        aresetn = 0;
        repeat (3) @(negedge aclk);
        aresetn = 1;
        send(0, -8, 1);
        drain();

        // Touch every slot and interleave updates with output stalls.
        for (int i = 1; i < MAX_VOXELS; i++) send(i, -40 - (i % 60), 1);
        ready_mode = 1;
        for (int i = 0; i < 1500; i++) begin
            slot = int'($urandom_range(0, MAX_VOXELS-1));
            send(slot, int'($urandom()), 0, (i % 17 == 0));
        end
        ready_mode = 0;
        drain();

        // Measure accepted input spacing directly, independently of time units.
        base_received = received;
        check_burst = 1;
        for (int i = 0; i < 20; i++) send(0, -1, i == 0);
        check_burst = 0;
        if (burst_accepted != 20) $fatal(1, "Lost burst inputs");
        drain();
        if (received - base_received != 20) $fatal(1, "Lost burst responses");
        if (accepted != received + aborted || aborted != 2)
            $fatal(1, "Transaction accounting mismatch");
        if (COUNT_WIDTH <= 4 && overflow_results == 0)
            $fatal(1, "Overflow case not exercised");
        $display("PASS MAX=%0d COUNT=%0d: received=%0d aborted=%0d rejected=%0d overflow=%0d stalled=%0d",
                 MAX_VOXELS, COUNT_WIDTH, received, aborted,
                 rejected_results, overflow_results, stalled_cycles);
        done = 1;
    end
endmodule

module tb_voxel_accumulator;
    wire [2:0] done;
    accumulator_case #(.MAX_VOXELS(1), .COUNT_WIDTH(3)) single_slot(done[0]);
    accumulator_case #(.MAX_VOXELS(5), .COUNT_WIDTH(3)) small_map(done[1]);
    accumulator_case #(.MAX_VOXELS(1024), .COUNT_WIDTH(32)) default_map(done[2]);
    initial begin
        wait (&done);
        $display("PASS: all accumulator configurations");
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "Accumulator test timed out");
    end
endmodule
