/*
Author: Sanat Konda
Updated: Oct 5, 2026

Purpose: Verify RF packet input through voxel lookup, accumulation, and DMA readout.
An independent model checks coordinates, sums, counts, metadata, malformed framing, and stalls.
*/

`timescale 1ns/1ps

module dma_pipeline_case #(parameter int COUNT_WIDTH = 32) (output bit done);
    localparam int MAX_VOXELS = 8;
    localparam longint unsigned COUNT_LIMIT = (64'd1 << COUNT_WIDTH) - 1;
    bit aclk = 0;
    always #5 aclk = ~aclk;
    logic aresetn = 0;
    logic [31:0] tx_data = 0;
    logic tx_valid = 0, tx_last = 0;
    wire tx_ready;
    wire [31:0] echo_data, rx_data;
    wire echo_valid, echo_ready, echo_last, rx_valid, rx_last;
    wire [3:0] rx_keep;
    logic rx_ready = 0;
    wire signed [31:0] x_mm, y_mm, z_mm, rssi_dbm, voxel_rssi_dbm, lookup_rssi_dbm;
    wire signed [32:0] voxel_x, voxel_y, voxel_z;
    wire observation_valid, observation_ready, voxel_valid, voxel_ready;
    wire [2:0] lookup_slot, acc_slot;
    wire lookup_new, lookup_rejected, lookup_valid, lookup_ready;
    wire init_done, map_full;
    wire [3:0] used_voxels;
    wire signed [COUNT_WIDTH+31:0] acc_rssi_sum;
    wire [COUNT_WIDTH-1:0] acc_count;
    wire acc_new, acc_rejected, acc_overflow, acc_valid, acc_ready;
    wire [31:0] observation_drone_id, voxel_drone_id, lookup_drone_id, acc_drone_id;
    wire [63:0] observation_timestamp_us, voxel_timestamp_us, lookup_timestamp_us, acc_timestamp_us;
    int cycle = 0, request_number = 0, malformed = 0, observations = 0;

    rf_packet_unpacker_wrapper unpacker (
        .aclk, .aresetn, .s_axis_tdata(tx_data), .s_axis_tvalid(tx_valid),
        .s_axis_tready(tx_ready), .s_axis_tlast(tx_last),
        .m_axis_tdata(echo_data), .m_axis_tvalid(echo_valid),
        .m_axis_tready(echo_ready), .m_axis_tlast(echo_last),
        .x_mm, .y_mm, .z_mm, .rssi_dbm, .observation_valid, .observation_ready,
        .observation_drone_id, .observation_timestamp_us
    );
    voxel_wrapper converter (
        .aclk, .aresetn, .x_mm, .y_mm, .z_mm, .rssi_dbm,
        .observation_drone_id, .observation_timestamp_us,
        .observation_valid, .observation_ready, .voxel_x, .voxel_y, .voxel_z,
        .voxel_drone_id, .voxel_timestamp_us,
        .voxel_rssi_dbm, .voxel_valid, .voxel_ready
    );
    voxel_lookup_wrapper #(.MAX_VOXELS(MAX_VOXELS), .TABLE_SIZE(16)) lookup (
        .aclk, .aresetn, .voxel_x, .voxel_y, .voxel_z, .voxel_rssi_dbm,
        .voxel_drone_id, .voxel_timestamp_us, .lookup_drone_id, .lookup_timestamp_us,
        .voxel_valid, .voxel_ready, .lookup_slot, .lookup_rssi_dbm,
        .lookup_new, .lookup_rejected, .lookup_valid, .lookup_ready,
        .init_done, .map_full, .used_voxels
    );
    voxel_accumulator_wrapper #(.MAX_VOXELS(MAX_VOXELS), .COUNT_WIDTH(COUNT_WIDTH)) accumulator (
        .aclk, .aresetn, .lookup_slot, .lookup_rssi_dbm, .lookup_new,
        .lookup_drone_id, .lookup_timestamp_us, .acc_drone_id, .acc_timestamp_us,
        .lookup_rejected, .lookup_valid, .lookup_ready, .acc_slot,
        .acc_rssi_sum, .acc_count, .acc_new, .acc_rejected,
        .acc_overflow, .acc_valid, .acc_ready
    );
    voxel_dma_readout_wrapper #(.MAX_VOXELS(MAX_VOXELS), .COUNT_WIDTH(COUNT_WIDTH)) readout (
        .aclk, .aresetn, .s_axis_tdata(echo_data), .s_axis_tvalid(echo_valid),
        .s_axis_tready(echo_ready), .s_axis_tlast(echo_last),
        .acc_slot, .acc_rssi_sum, .acc_count, .acc_new, .acc_rejected,
        .acc_drone_id, .acc_timestamp_us,
        .acc_overflow, .acc_valid, .acc_ready,
        .m_axis_tdata(rx_data), .m_axis_tkeep(rx_keep), .m_axis_tvalid(rx_valid),
        .m_axis_tready(rx_ready), .m_axis_tlast(rx_last)
    );

    logic [31:0] expected[$], wanted;
    logic [98:0] keys[MAX_VOXELS];
    longint signed sums[MAX_VOXELS];
    int unsigned counts[MAX_VOXELS];
    logic signed [31:0] input_words[7];
    int occupied = 0, accepted = 0, received = 0, rejected = 0, overflows = 0;
    int input_position = 0, output_position = 0, input_stalls = 0;
    int input_beats = 0, echo_beats = 0, output_stalls = 0;
    logic [36:0] held_payload;
    bit held = 0;

    function automatic logic signed [32:0] floor_voxel(input int signed position);
        longint signed v;
        v = longint'(position);
        return 33'(v >= 0 ? v / 500 : -((-v + 499) / 500));
    endfunction

    always @(negedge aclk) begin
        cycle++;
        // Long stalls exercise upstream propagation; the echo must still drain.
        rx_ready = ((cycle % 61) >= 40);
    end

    always @(posedge aclk) begin : scoreboard
        logic [98:0] key;
        int slot;
        logic [31:0] flags;
        longint signed sum_value;
        int unsigned count_value;
        if (!aresetn) begin
            if (expected.size() != 0) $fatal(1, "Test reset before draining");
            occupied = 0;
            input_position = 0;
            output_position = 0;
            held = 0;
        end else begin
            if (observation_valid && observation_ready) observations++;
            if (!echo_ready) $fatal(1, "Echo drain stalled after reset");
            if (echo_valid && echo_ready) echo_beats++;
            if (tx_valid && !tx_ready) input_stalls++;
            if (held && (!rx_valid || {rx_last, rx_keep, rx_data} !== held_payload))
                $fatal(1, "DMA output changed while stalled");
            held = rx_valid && !rx_ready;
            held_payload = {rx_last, rx_keep, rx_data};
            if (held) output_stalls++;

            if (tx_valid && tx_ready) begin
                input_beats++;
                if (input_position < 7) input_words[input_position] = $signed(tx_data);
                if (tx_last && input_position == 6) begin
                    key = {floor_voxel(input_words[0]), floor_voxel(input_words[1]),
                           floor_voxel(input_words[2])};
                    slot = -1;
                    flags = 0;
                    sum_value = 0;
                    count_value = 0;
                    for (int i = 0; i < occupied; i++)
                        if (keys[i] == key) slot = i;
                    if (slot == -1 && occupied < MAX_VOXELS) begin
                        slot = occupied++;
                        keys[slot] = key;
                        sums[slot] = 0;
                        counts[slot] = 0;
                        flags = 1;
                    end
                    if (slot == -1) begin
                        flags = 2;
                        rejected++;
                    end else begin
                        if (64'(counts[slot]) == COUNT_LIMIT) begin
                            flags = 6;
                            overflows++;
                        end else begin
                            sums[slot] += longint'(input_words[3]);
                            counts[slot]++;
                        end
                        sum_value = sums[slot];
                        count_value = counts[slot];
                    end
                    expected.push_back(slot == -1 ? 32'd0 : 32'(slot));
                    expected.push_back(32'(sum_value));
                    expected.push_back(32'(sum_value >>> 32));
                    expected.push_back(count_value);
                    expected.push_back(flags);
                    expected.push_back(input_words[4]);
                    expected.push_back(input_words[5]);
                    expected.push_back(input_words[6]);
                    accepted++;
                end else if (tx_last) malformed++;
                if (tx_last) input_position = 0;
                else input_position++;
            end

            if (rx_valid && rx_ready) begin
                if (expected.size() == 0) $fatal(1, "Unexpected DMA output word");
                wanted = expected.pop_front();
                if (rx_data !== wanted || rx_keep !== 4'hf || rx_last !== (output_position == 7))
                    $fatal(1, "COUNT=%0d packet=%0d word=%0d got=%h expected=%h",
                           COUNT_WIDTH, received, output_position, rx_data, wanted);
                if (output_position == 7) begin
                    received++;
                    output_position = 0;
                end else output_position++;
            end
        end
    end

    task automatic send(input int signed x, y, z, rssi);
        logic [31:0] packet[7];
        logic [31:0] id;
        logic [63:0] timestamp_us;
        case (request_number % 4)
            0: id = 101;
            1: id = 202;
            2: id = 0;
            default: id = 32'hffffffff;
        endcase
        case (request_number % 5)
            0: timestamp_us = 64'd0;
            1: timestamp_us = 64'h00000000ffffffff;
            2: timestamp_us = 64'h0000000100000000;
            3: timestamp_us = 64'hffffffffffffffff;
            default: timestamp_us = {32'(request_number), ~32'(request_number)};
        endcase
        request_number++;
        packet = '{32'(x), 32'(y), 32'(z), 32'(rssi), id,
                   timestamp_us[31:0], timestamp_us[63:32]};
        for (int i = 0; i < 7; i++) begin
            @(negedge aclk);
            tx_data = packet[i];
            tx_last = (i == 6);
            tx_valid = 1;
            do @(posedge aclk); while (!tx_ready);
        end
        @(negedge aclk);
        tx_valid = 0;
        tx_last = 0;
    endtask

    // Malformed packets must echo and drain but produce no observation.
    task automatic send_bad(input int beats, input bit terminate_packet = 1);
        for (int i = 0; i < beats; i++) begin
            @(negedge aclk);
            tx_data = 32'(i);
            tx_valid = 1;
            tx_last = terminate_packet && (i == beats-1);
            do @(posedge aclk); while (!tx_ready);
        end
        @(negedge aclk);
        tx_valid = 0;
        tx_last = 0;
    endtask

    task automatic drain;
        wait (expected.size() == 0);
        repeat (4) @(negedge aclk);
    endtask

    initial begin
        repeat (4) @(negedge aclk);
        aresetn = 1;
        for (int n = 1; n < 7; n++) send_bad(n);
        send_bad(8);
        send_bad(17);
        send(1250, 500, 1750, -63);
        send(1250, 500, 1750, -67);
        send(1750, 500, 1750, -70);
        send(1250, 500, 1750, -63);
        drain();
        if (used_voxels != 2) $fatal(1, "Wrong initial allocation count");
        // Reset with a partial packet buffered, then accept a fresh frame.
        send_bad(5, 0);
        aresetn = 0;
        repeat (4) @(negedge aclk);
        aresetn = 1;
        send(1250, 500, 1750, -63);
        send(1750, 500, 1750, -70);
        send(-1, -500, -501, -2147483648);
        send(-2147483648, 2147483647, 0, 2147483647);
        for (int i = 0; i < 1000; i++) begin
            case (i % 5)
                0: send(1250, 500, 1750, -63);
                1: send(1750, 500, 1750, -67);
                2: send(-1, -500, -501, -2147483648);
                3: send(-2147483648, 2147483647, 0, 2147483647);
                default: send(i * 500, -1000, 2500, -90);
            endcase
        end
        drain();
        if (accepted != received || rejected == 0 || input_stalls == 0 ||
            output_stalls == 0 || input_beats != echo_beats ||
            malformed != 8 || observations != accepted ||
            (COUNT_WIDTH == 3 && overflows == 0) ||
            int'(used_voxels) != MAX_VOXELS || !map_full || !init_done)
            $fatal(1, "Pipeline coverage/accounting failure");
        $display("PASS DMA pipeline COUNT=%0d: packets=%0d full_rejections=%0d overflows=%0d input_stalls=%0d",
                 COUNT_WIDTH, received, rejected, overflows, input_stalls);
        done = 1;
    end
endmodule

module tb_voxel_dma_pipeline;
    wire [1:0] done;
    dma_pipeline_case #(.COUNT_WIDTH(32)) normal(done[0]);
    dma_pipeline_case #(.COUNT_WIDTH(3)) overflow_test(done[1]);
    initial begin
        wait (&done);
        $display("PASS all DMA pipeline configurations");
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "DMA pipeline test timed out");
    end
endmodule
