/*
Author: Sanat Konda
Updated: Sept 25, 2026

Purpose: Verify voxel conversion, sparse lookup, and RSSI accumulation together.
An independent coordinate-to-statistics model checks stalls, map-full rejection, and reset.
*/

`timescale 1ns/1ps

module tb_voxel_accumulator_pipeline;
    localparam int MAX_VOXELS = 8;
    bit aclk = 0;
    always #5 aclk = ~aclk;
    logic aresetn = 0, observation_valid = 0;
    logic signed [31:0] x_mm = 0, y_mm = 0, z_mm = 0, rssi_dbm = 0;
    wire observation_ready, voxel_valid, voxel_ready;
    wire signed [32:0] voxel_x, voxel_y, voxel_z;
    wire signed [31:0] voxel_rssi_dbm, lookup_rssi_dbm;
    wire [2:0] lookup_slot, acc_slot;
    wire lookup_new, lookup_rejected, lookup_valid, lookup_ready;
    wire init_done, map_full;
    wire [3:0] used_voxels;
    wire signed [63:0] acc_rssi_sum;
    wire [31:0] acc_count;
    wire acc_new, acc_rejected, acc_overflow, acc_valid;
    logic acc_ready = 0;
    int cycle = 0;

    voxel converter (
        .aclk, .aresetn, .x_mm, .y_mm, .z_mm, .rssi_dbm,
        .observation_valid, .observation_ready, .voxel_x, .voxel_y, .voxel_z,
        .voxel_rssi_dbm, .voxel_valid, .voxel_ready
    );
    voxel_lookup_wrapper #(.MAX_VOXELS(MAX_VOXELS), .TABLE_SIZE(16)) lookup (
        .aclk, .aresetn, .voxel_x, .voxel_y, .voxel_z, .voxel_rssi_dbm,
        .voxel_valid, .voxel_ready, .lookup_slot, .lookup_rssi_dbm,
        .lookup_new, .lookup_rejected, .lookup_valid, .lookup_ready,
        .init_done, .map_full, .used_voxels
    );
    voxel_accumulator_wrapper #(.MAX_VOXELS(MAX_VOXELS)) accumulator (
        .aclk, .aresetn, .lookup_slot, .lookup_rssi_dbm, .lookup_new,
        .lookup_rejected, .lookup_valid, .lookup_ready, .acc_slot,
        .acc_rssi_sum, .acc_count, .acc_new, .acc_rejected,
        .acc_overflow, .acc_valid, .acc_ready
    );

    typedef struct packed {
        logic [2:0] slot;
        logic signed [63:0] sum;
        logic [31:0] count;
        bit is_new, rejected;
    } result_t;
    result_t expected[$], result;
    logic [98:0] keys [MAX_VOXELS];
    longint signed sums [MAX_VOXELS];
    int unsigned counts [MAX_VOXELS];
    int occupied = 0, accepted = 0, received = 0, rejected = 0, input_stalls = 0;

    function automatic logic signed [32:0] floor_voxel(input int signed position);
        longint signed v;
        v = longint'(position);
        return 33'(v >= 0 ? v / 500 : -((-v + 499) / 500));
    endfunction

    always @(negedge aclk) begin
        cycle++;
        acc_ready = ((cycle % 23) >= 8);
    end

    always @(posedge aclk) begin : scoreboard
        logic [98:0] key;
        int slot;
        if (!aresetn) begin
            if (expected.size() != 0) $fatal(1, "Test reset before draining");
            occupied = 0;
        end else begin
            if (observation_valid && !observation_ready) input_stalls++;
            if (observation_valid && observation_ready) begin
                key = {floor_voxel(x_mm), floor_voxel(y_mm), floor_voxel(z_mm)};
                slot = -1;
                for (int i = 0; i < occupied; i++)
                    if (keys[i] == key) slot = i;
                result = '0;
                if (slot == -1 && occupied < MAX_VOXELS) begin
                    slot = occupied++;
                    keys[slot] = key;
                    sums[slot] = 0;
                    counts[slot] = 0;
                    result.is_new = 1;
                end
                if (slot == -1) begin
                    result.rejected = 1;
                end else begin
                    sums[slot] += longint'(rssi_dbm);
                    counts[slot]++;
                    result.slot = 3'(slot);
                    result.sum = sums[slot];
                    result.count = counts[slot];
                end
                expected.push_back(result);
                accepted++;
            end
            if (acc_valid && acc_ready) begin
                if (expected.size() == 0) $fatal(1, "Unexpected pipeline result");
                result = expected.pop_front();
                if ({acc_slot, acc_rssi_sum, acc_count, acc_new, acc_rejected} !== result || acc_overflow)
                    $fatal(1, "Pipeline mismatch at response %0d", received);
                received++;
                if (acc_rejected) rejected++;
            end
        end
    end

    task automatic send(input int signed x, y, z, rssi);
        @(negedge aclk);
        x_mm = x; y_mm = y; z_mm = z; rssi_dbm = rssi;
        observation_valid = 1;
        do @(posedge aclk); while (!observation_ready);
        @(negedge aclk);
        observation_valid = 0;
    endtask

    task automatic drain;
        wait (expected.size() == 0);
        repeat (4) @(negedge aclk);
    endtask

    initial begin
        repeat (4) @(negedge aclk);
        aresetn = 1;
        send(1250, 500, 1750, -63);
        send(1250, 500, 1750, -67);
        send(1750, 500, 1750, -70);
        send(1250, 500, 1750, -63);
        drain();
        if (used_voxels != 2) $fatal(1, "Unexpected number of allocated voxels");

        // Lookup and accumulator must restart together; statistics RAM stays uncleared.
        aresetn = 0;
        repeat (4) @(negedge aclk);
        aresetn = 1;
        send(1250, 500, 1750, -63);
        send(1750, 500, 1750, -70);
        send(-1, -500, -501, -2147483648);
        send(-2147483648, 2147483647, 0, 2147483647);
        for (int i = 0; i < 2000; i++) begin
            case (i % 5)
                0: send(1250, 500, 1750, -63);
                1: send(1750, 500, 1750, -67);
                2: send(-1, -500, -501, -80);
                3: send(-2147483648, 2147483647, 0, 2147483647);
                default: send(i * 500, -1000, 2500, -90);
            endcase
        end
        drain();
        if (accepted != received || rejected == 0 || input_stalls == 0 ||
            int'(used_voxels) != MAX_VOXELS || !map_full || !init_done)
            $fatal(1, "Pipeline coverage/accounting failure");
        $display("PASS pipeline: %0d observations/results, %0d rejected, %0d upstream stall cycles",
                 received, rejected, input_stalls);
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "Pipeline test timed out");
    end
endmodule
