/*
Author: Sanat Konda
Updated: Sept 24, 2026

Purpose: Verify sparse voxel allocation against an independent key-to-slot model.
Check collisions, signed keys, stalls, reset, and capacity across four configurations.
*/

`timescale 1ns/1ps

module voxel_lookup_test #(
    parameter int MAX_VOXELS = 5,
    parameter int TABLE_SIZE = 8
) (
    output logic done = 1'b0
);
    localparam int SLOT_WIDTH = (MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1;
    localparam int CHAIN_LENGTH = (MAX_VOXELS < 16) ? MAX_VOXELS : 16;
    logic signed [32:0] collision_x [CHAIN_LENGTH];

    logic aclk = 1'b0;
    always #5 aclk = ~aclk;

    logic aresetn = 1'b0;
    logic signed [32:0] voxel_x = '0, voxel_y = '0, voxel_z = '0;
    logic signed [31:0] voxel_rssi_dbm = '0;
    logic voxel_valid = 1'b0, voxel_ready;
    logic [SLOT_WIDTH-1:0] lookup_slot;
    logic signed [31:0] lookup_rssi_dbm;
    logic lookup_new, lookup_rejected, lookup_valid;
    logic lookup_ready = 1'b1;
    logic init_done, map_full;
    logic [$clog2(MAX_VOXELS+1)-1:0] used_voxels;

    voxel_lookup_wrapper #(
        .MAX_VOXELS(MAX_VOXELS), .TABLE_SIZE(TABLE_SIZE)
    ) dut (.*);

    typedef struct packed {
        logic [SLOT_WIDTH-1:0] slot;
        logic signed [31:0] rssi;
        logic is_new, rejected;
        int count_after, accepted_cycle;
    } response_t;

    logic [98:0] model_keys [$];
    response_t expected [$];
    logic [SLOT_WIDTH+33:0] stalled_payload;
    bit was_stalled = 0;
    bit random_sink = 0, force_ready = 1;
    int cycles = 0, accepted = 0, received = 0, aborted = 0;
    int new_count = 0, hit_count = 0, reject_count = 0;
    int stall_checks = 0, max_latency = 0;
    int unsigned sink_rng = 32'h1253abcd ^ MAX_VOXELS;
    int unsigned source_rng = 32'h73a6214f ^ TABLE_SIZE;

    function automatic int unsigned random_word(ref int unsigned seed);
        seed ^= seed << 13;
        seed ^= seed >> 17;
        seed ^= seed << 5;
        return seed;
    endfunction

    always @(negedge aclk)
        lookup_ready = random_sink ? ((random_word(sink_rng) % 4) != 0) :
                                     force_ready;

    // The reference model compares complete keys, independent of the RTL hash.
    always @(posedge aclk) begin : scoreboard
        response_t item;
        logic [98:0] key;
        int slot;

        cycles++;
        if (!aresetn) begin
            aborted += expected.size();
            expected.delete();
            model_keys.delete();
            was_stalled = 0;
        end else begin
            if (!init_done && (voxel_ready || lookup_valid))
                $fatal(1, "Traffic enabled before initialization");

            if (was_stalled) begin
                if (!lookup_valid ||
                    {lookup_slot, lookup_rssi_dbm, lookup_new, lookup_rejected}
                        !== stalled_payload)
                    $fatal(1, "Output changed under backpressure");
                stall_checks++;
            end
            was_stalled = lookup_valid && !lookup_ready;
            stalled_payload = {lookup_slot, lookup_rssi_dbm,
                               lookup_new, lookup_rejected};

            if (voxel_valid && voxel_ready) begin
                key = {voxel_x, voxel_y, voxel_z};
                slot = -1;
                foreach (model_keys[i])
                    if (model_keys[i] == key)
                        slot = i;

                item = '0;
                item.rssi = voxel_rssi_dbm;
                item.accepted_cycle = cycles;
                if (slot >= 0) begin
                    item.slot = SLOT_WIDTH'(slot);
                end else if (model_keys.size() < MAX_VOXELS) begin
                    item.slot = SLOT_WIDTH'(model_keys.size());
                    item.is_new = 1'b1;
                    model_keys.push_back(key);
                end else begin
                    item.rejected = 1'b1;
                end
                item.count_after = model_keys.size();
                expected.push_back(item);
                accepted++;
            end

            if (lookup_valid && lookup_ready) begin
                if (expected.size() == 0)
                    $fatal(1, "Unexpected response");
                item = expected.pop_front();
                if ({lookup_slot, lookup_rssi_dbm, lookup_new, lookup_rejected}
                    !== {item.slot, item.rssi, item.is_new, item.rejected})
                    $fatal(1, "Response mismatch MAX=%0d response=%0d",
                           MAX_VOXELS, received);
                if (int'(used_voxels) != item.count_after ||
                    map_full !== (item.count_after == MAX_VOXELS))
                    $fatal(1, "Allocation count/full status mismatch");
                received++;
                if (item.rejected) reject_count++;
                else if (item.is_new) new_count++;
                else hit_count++;
                if (cycles-item.accepted_cycle > max_latency)
                    max_latency = cycles-item.accepted_cycle;
            end
        end
    end

    task automatic send(
        input logic signed [32:0] x, y, z,
        input logic signed [31:0] rssi
    );
        @(negedge aclk);
        voxel_x = x;
        voxel_y = y;
        voxel_z = z;
        voxel_rssi_dbm = rssi;
        voxel_valid = 1'b1;
        do @(posedge aclk); while (!voxel_ready);
        @(negedge aclk);
        voxel_valid = 1'b0;
    endtask

    task automatic drain;
        do @(negedge aclk); while (expected.size() != 0 || lookup_valid);
    endtask

    task automatic reset_map;
        int clear_cycles;
        @(negedge aclk);
        aresetn = 1'b0;
        voxel_valid = 1'b0;
        random_sink = 0;
        force_ready = 1;
        repeat (3) @(negedge aclk);
        aresetn = 1'b1;
        clear_cycles = 0;
        do begin
            @(negedge aclk);
            clear_cycles++;
        end while (!init_done);
        if (clear_cycles != TABLE_SIZE || used_voxels != 0 || map_full)
            $fatal(1, "Incorrect initialization duration/state");
    endtask

    initial begin : stimulus
        int unsigned value;
        int key_index, found;
        logic [98:0] key;

        reset_map();
        send(33'sd2, 33'sd1, 33'sd3, -63);
        send(33'sd2, 33'sd1, 33'sd3, -42);
        send(-33'sd1, -33'sd2, -33'sd3, -100);
        send(33'sh100000000, 33'sh0ffffffff, 0, 32'sh80000000);
        send(33'sh0ffffffff, 33'sh100000000, 0, 32'sh7fffffff);
        send(0, 0, 0, -1);
        send(33'sh100000000, 0, 0, -2);
        send(0, 33'sh100000000, 0, -3);
        send(0, 0, 33'sh100000000, -4);
        drain();

        reset_map();
        // Use the hash only to construct collisions; expected results above
        // still come from the independent full-key reference model.
        found = 0;
        for (int candidate = 0; found < CHAIN_LENGTH; candidate++) begin
            key = {33'(candidate), 66'b0};
            if (int'(dut.voxel_lookup_inst.hash_key(key)) == TABLE_SIZE-1) begin
                collision_x[found] = 33'(candidate);
                found++;
            end
            if (candidate == 1000000)
                $fatal(1, "Could not construct collision test keys");
        end
        for (int i = 0; i < CHAIN_LENGTH; i++)
            send(collision_x[i], 0, 0, -i-20);
        for (int i = 0; i < CHAIN_LENGTH; i++)
            send(collision_x[i], 0, 0, -i-40);
        drain();
        if (max_latency < CHAIN_LENGTH+1)
            $fatal(1, "Collision chain was not exercised");

        force_ready = 0;
        send(collision_x[0], 0, 0, -77);
        wait (lookup_valid);
        repeat (25) @(negedge aclk);
        if (voxel_ready)
            $fatal(1, "Accepted work without response space");
        force_ready = 1;
        drain();

        // Reset cancels a held response and discards every previous mapping.
        force_ready = 0;
        send(collision_x[0], 0, 0, -78);
        wait (lookup_valid);
        reset_map();

        if (CHAIN_LENGTH >= 3) begin
            for (int i = 0; i < CHAIN_LENGTH; i++)
                send(collision_x[i], 0, 0, -30);
            drain();
            send(collision_x[CHAIN_LENGTH-1], 0, 0, -31);
            reset_map(); // Interrupt a collision search before its response.
        end

        // Restart reset partway through its clearing sweep.
        @(negedge aclk);
        aresetn = 1'b0;
        repeat (2) @(negedge aclk);
        aresetn = 1'b1;
        repeat (TABLE_SIZE/2) @(negedge aclk);
        reset_map();

        random_sink = 1;
        for (int i = 0; i < MAX_VOXELS; i++)
            send(33'(i), 0, 0, -50);
        drain();
        if (!map_full || int'(used_voxels) != MAX_VOXELS)
            $fatal(1, "Did not reach full capacity");

        send(33'(MAX_VOXELS), 0, 0, -99); // Must reject, including full tables.
        for (int i = 0; i < MAX_VOXELS; i++)
            send(33'(i), 0, 0, -60); // Existing slots still work when full.

        for (int i = 0; i < 1000; i++) begin
            value = random_word(source_rng);
            if ((value % 4) != 0) begin
                key_index = int'(value % MAX_VOXELS);
                key = model_keys[key_index];
                send($signed(key[98:66]), $signed(key[65:33]),
                     $signed(key[32:0]), $signed(random_word(source_rng)));
            end else begin
                send(33'($signed(random_word(source_rng))),
                     33'($signed(random_word(source_rng))),
                     33'($signed(random_word(source_rng))),
                     $signed(random_word(source_rng)));
            end
            if ((value % 8) == 0)
                repeat (2) @(negedge aclk);
        end
        drain();

        if (accepted != received+aborted || new_count == 0 || hit_count == 0 ||
            reject_count == 0 || stall_checks < 25 || aborted == 0)
            $fatal(1, "Missing coverage or transaction accounting failure");
        $display("PASS MAX=%0d TABLE=%0d accepted=%0d received=%0d aborted=%0d stalls=%0d max_latency=%0d",
                 MAX_VOXELS, TABLE_SIZE, accepted, received, aborted,
                 stall_checks, max_latency);
        done = 1'b1;
    end
endmodule

module tb_voxel_lookup;
    wire [3:0] done;
    voxel_lookup_test #(.MAX_VOXELS(1), .TABLE_SIZE(2)) single_slot(done[0]);
    voxel_lookup_test #(.MAX_VOXELS(5), .TABLE_SIZE(8)) non_power_two(done[1]);
    voxel_lookup_test #(.MAX_VOXELS(8), .TABLE_SIZE(8)) full_table(done[2]);
    voxel_lookup_test #(.MAX_VOXELS(1024), .TABLE_SIZE(2048)) defaults(done[3]);

    initial begin
        wait (&done);
        $display("PASS: all voxel lookup configurations");
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1, "Testbench timeout");
    end
endmodule
