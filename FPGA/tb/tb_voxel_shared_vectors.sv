/*
Author: Sanat Konda
Updated: Oct 5, 2026

Purpose: Verify RF packet input through voxel lookup, accumulation, and DMA readout.
An independent model checks coordinates, sums, counts, metadata, malformed framing, and stalls.
*/

`timescale 1ns/1ps

module tb_voxel_shared_vectors;
    localparam int COUNT_WIDTH = 32;
    localparam int MAX_VOXELS = 1024;
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
    wire [9:0] lookup_slot, acc_slot;
    wire lookup_new, lookup_rejected, lookup_valid, lookup_ready;
    wire init_done, map_full;
    wire [10:0] used_voxels;
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
    voxel_lookup_wrapper #(.MAX_VOXELS(MAX_VOXELS), .TABLE_SIZE(2048)) lookup (
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
    int starts[$], started;
    logic [36:0] held_payload;
    bit held = 0, no_stalls = 0;
    int ready_mode = 2, remaining_stall = 0;
    int submitted = 0, completed = 0, aborted = 0, accepted = 0, rejected = 0;
    int position = 0, words = 0, stalls = 0, max_latency = 0, total_latency = 0;
    int min_latency = 2147483647, first_cycle = 0, last_cycle = 0;
    int unsigned sink_rng, source_rng, seed;
    string vector_path;
    int fd, scanned;
    logic [31:0] row[15];
    function automatic int unsigned random_word(ref int unsigned state);
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        return state;
    endfunction
    always @(negedge aclk) begin
        if (ready_mode == 2) rx_ready = 0;
        else if (no_stalls) rx_ready = 1;
        else if (remaining_stall > 0) begin
            rx_ready = 0; remaining_stall--;
        end else if (random_word(sink_rng) % 127 == 0) begin
            remaining_stall = int'(random_word(sink_rng) % 1000); rx_ready = 0;
        end else rx_ready = (random_word(sink_rng) % 4 != 0);
    end
    always @(posedge aclk) begin
        cycle++;
        if (!aresetn) begin
            held = 0;
        end else begin
            if ($isunknown({tx_ready, rx_valid, observation_valid, voxel_valid, lookup_valid, acc_valid}))
                $fatal(1, "Unknown valid/control after reset");
            if (held && (rx_valid !== 1'b1 || {rx_last, rx_keep, rx_data} !== held_payload))
                $fatal(1, "Readout payload changed under stall");
            held = rx_valid && !rx_ready;
            if (held) stalls++;
            held_payload = {rx_last, rx_keep, rx_data};
            if (tx_valid && tx_ready && tx_last) begin
                starts.push_back(cycle); submitted++;
                if (submitted == 2) first_cycle = cycle;
            end
            if (rx_valid && rx_ready) begin
                if (!expected.size()) $fatal(1, "Unexpected or duplicate output");
                wanted = expected.pop_front();
                if (rx_data !== wanted || rx_keep !== 4'hf || rx_last !== (position == 7))
                    $fatal(1, "Shared vector result=%0d word=%0d got=%h expected=%h", completed,position,rx_data,wanted);
                if (position == 4) begin
                    if (rx_data & 2) rejected++; else accepted++;
                end
                position = (position + 1) % 8;
                words++;
                if (position == 0) begin
                    completed++;
                    started = starts.pop_front();
                    last_cycle = cycle;
                    total_latency += cycle-started;
                    if (cycle-started < min_latency) min_latency=cycle-started;
                    if (cycle-started > max_latency) max_latency=cycle-started;
                end
            end
        end
    end
    task automatic send_row;
        for (int i=7;i<15;i++) expected.push_back(row[i]);
        for (int i=0;i<7;i++) begin
            @(negedge aclk);
            tx_valid=0;
            repeat (no_stalls ? 0 : random_word(source_rng)%3) @(negedge aclk);
            tx_data=row[i]; tx_last=(i==6); tx_valid=1;
            do @(posedge aclk); while (tx_ready !== 1'b1);
        end
        @(negedge aclk); tx_valid=0; tx_last=0;
    endtask
    initial begin
        if (!$value$plusargs("VECTORS=%s",vector_path)) $fatal(1,"VECTORS path required");
        if (!$value$plusargs("SEED=%d",seed)) seed=1;
        no_stalls=$test$plusargs("NO_STALL");
        sink_rng=seed; source_rng=seed ^ 32'h718af12b;
        fd=$fopen(vector_path,"r"); if (!fd) $fatal(1,"Cannot open vectors");
        repeat(4) @(negedge aclk); aresetn=1;
        // Submit during initialization, hold a complete result, then coordinated reset.
        row='{0,0,0,32'hffffffc1,101,0,0,0,32'hffffffc1,32'hffffffff,1,1,101,0,0};
        send_row(); wait(rx_valid); repeat(10) @(negedge aclk);
        aresetn=0; aborted++; expected.delete(); starts.delete();
        repeat(4) @(negedge aclk); aresetn=1; ready_mode=0;
        while (!$feof(fd)) begin
            scanned=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h",
                row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],row[9],row[10],row[11],row[12],row[13],row[14]);
            if (scanned==15) send_row();
            else if (scanned!=-1 && scanned!=0) $fatal(1,"Malformed vector row");
        end
        $fclose(fd);
        wait(expected.size()==0); repeat(20) @(negedge aclk);
        if (submitted != completed+aborted || accepted+rejected!=completed ||
            words != completed*8 || used_voxels!=1024 || !map_full || !init_done ||
            starts.size()!=0 || stalls==0 || rejected==0) $fatal(1,"Accounting/coverage failure");
        $display("PASS shared vectors seed=%0d submitted=%0d completed=%0d accepted=%0d rejected=%0d reset_aborted=%0d cycles=%0d total_latency=%0d max_latency=%0d stalls=%0d min_latency=%0d measured_cycles=%0d no_stalls=%0d",
                 seed,submitted,completed,accepted,rejected,aborted,cycle,total_latency,max_latency,stalls,min_latency,last_cycle-first_cycle+1,no_stalls);
        $finish;
    end
    initial begin
        #1000000000; $fatal(1,"Shared vector watchdog");
    end
endmodule
