`timescale 1ns/1ps

// Check unpacker -> voxel handshakes with independent AXI and voxel sink stalls.
// From FPGA/tb with Vivado tools on PATH:
// xvlog -sv ../rtl/rf_packet_unpacker.sv ../rtl/rf_packet_unpacker_wrapper.v ../rtl/voxel.sv ../rtl/voxel_wrapper.v rf_voxel_pipeline_tb.sv
// xelab rf_voxel_pipeline_tb -s rf_voxel_pipeline_tb_sim --timescale 1ns/1ps
// xsim rf_voxel_pipeline_tb_sim -runall
module rf_voxel_pipeline_tb;
    logic aclk = 1'b0;
    always #5 aclk = ~aclk;
    logic aresetn = 1'b0;
    logic [31:0] s_axis_tdata = '0, m_axis_tdata;
    logic s_axis_tvalid = 1'b0, s_axis_tready, s_axis_tlast = 1'b0;
    logic m_axis_tvalid, m_axis_tready = 1'b1, m_axis_tlast;
    logic signed [31:0] x_mm, y_mm, z_mm, rssi_dbm, voxel_rssi_dbm;
    logic observation_valid, observation_ready;
    logic signed [32:0] vx, vy, vz;
    logic voxel_valid, voxel_ready = 1'b0;

    rf_packet_unpacker_wrapper unpacker (.*);
    voxel_wrapper voxelizer (.*);

    integer words [0:31];
    integer expected_vx [0:7], expected_vy [0:7], expected_vz [0:7];
    integer input_count = 0, forwarded_count = 0, voxel_count = 0;
    integer full_stalls = 0, axis_stalls = 0, voxel_stalls = 0;
    integer overlap_count = 0;
    logic previous_voxel_stall = 1'b0, previous_observation_stall = 1'b0;
    logic previous_axis_stall = 1'b0;
    logic [130:0] held_voxel;
    logic [127:0] held_observation;
    logic [32:0] held_axis;

    // Explicit expected coordinates test negative floor division independently.
    task automatic packet(
        input integer index, x, y, z, rssi, expect_x, expect_y, expect_z
    );
        words[4*index] = x;
        words[4*index+1] = y;
        words[4*index+2] = z;
        words[4*index+3] = rssi;
        expected_vx[index] = expect_x;
        expected_vy[index] = expect_y;
        expected_vz[index] = expect_z;
    endtask

    // Inspect the values receivers sample, before nonblocking register updates.
    always @(posedge aclk) begin
        if (!aresetn) begin
            previous_voxel_stall = 1'b0;
            previous_observation_stall = 1'b0;
            previous_axis_stall = 1'b0;
        end else begin
            if ((s_axis_tvalid && s_axis_tready) !==
                (m_axis_tvalid && m_axis_tready))
                $fatal(1, "AXI input and forwarding handshakes diverged");
            if (previous_voxel_stall &&
                (voxel_valid !== 1'b1 ||
                 {vx, vy, vz, voxel_rssi_dbm} !== held_voxel))
                $fatal(1, "Voxel changed or valid dropped before acceptance");
            if (previous_observation_stall &&
                (observation_valid !== 1'b1 ||
                 {x_mm, y_mm, z_mm, rssi_dbm} !== held_observation))
                $fatal(1, "Unpacker observation changed while voxelizer stalled");
            if (previous_axis_stall &&
                (m_axis_tvalid !== 1'b1 || {m_axis_tdata, m_axis_tlast} !== held_axis))
                $fatal(1, "Forwarded AXI word changed during a stall");

            if (s_axis_tvalid && s_axis_tready)
                input_count = input_count + 1;
            if (m_axis_tvalid && m_axis_tready) begin
                if (forwarded_count >= 32)
                    $fatal(1, "Duplicate forwarded AXI word");
                if (m_axis_tdata !== words[forwarded_count] ||
                    m_axis_tlast !== (forwarded_count % 4 == 3))
                    $fatal(1, "Forwarded word/TLAST mismatch at word %0d", forwarded_count);
                forwarded_count = forwarded_count + 1;
            end
            if (voxel_valid) begin
                if (voxel_count >= 8)
                    $fatal(1, "Unexpected duplicate voxel");
                if (vx !== 33'(expected_vx[voxel_count]) ||
                    vy !== 33'(expected_vy[voxel_count]) ||
                    vz !== 33'(expected_vz[voxel_count]) ||
                    voxel_rssi_dbm !== words[4*voxel_count+3])
                    $fatal(1, "Voxel %0d mismatch: (%0d,%0d,%0d) RSSI %0d",
                           voxel_count, vx, vy, vz, voxel_rssi_dbm);
                if (voxel_ready) begin
                    voxel_count = voxel_count + 1;
                    if (observation_valid && observation_ready)
                        overlap_count = overlap_count + 1;
                end
            end
            if (observation_valid && !observation_ready && s_axis_tvalid) begin
                full_stalls = full_stalls + 1;
                if (s_axis_tready !== 1'b0)
                    $fatal(1, "Full observation pipeline did not backpressure AXI");
            end
            previous_voxel_stall = voxel_valid && !voxel_ready;
            previous_observation_stall = observation_valid && !observation_ready;
            previous_axis_stall = m_axis_tvalid && !m_axis_tready;
            held_voxel = {vx, vy, vz, voxel_rssi_dbm};
            held_observation = {x_mm, y_mm, z_mm, rssi_dbm};
            held_axis = {m_axis_tdata, m_axis_tlast};
            if (previous_voxel_stall) voxel_stalls = voxel_stalls + 1;
            if (previous_axis_stall) axis_stalls = axis_stalls + 1;
        end
    end

    initial begin
        packet(0, 1200, 700, 600, -65, 2, 1, 1);
        packet(1, -1, -500, -501, -66, -1, -1, -2);
        packet(2, 0, 499, 500, -67, 0, 0, 1);
        packet(3, -1000, -999, 3999, -68, -2, -2, 7);
        packet(4, 32'sh7fffffff, 32'sh80000000, 2000, -69, 4294967, -4294968, 4);
        packet(5, 4000, 4000, 2000, -70, 8, 8, 4);
        packet(6, -4001, 1500, -1500, -71, -9, 3, -3);
        packet(7, 999, 1000, -1001, -72, 1, 2, -3);
        repeat (3) @(negedge aclk);
        aresetn = 1'b1;
        fork
            begin
                // Keep each source word stable until accepted; no extra bubbles.
                for (int index = 0; index < 32; index++) begin
                    s_axis_tdata = words[index];
                    s_axis_tlast = (index % 4 == 3);
                    s_axis_tvalid = 1'b1;
                    @(posedge aclk);
                    while (s_axis_tready !== 1'b1) @(posedge aclk);
                    @(negedge aclk);
                end
                s_axis_tvalid = 1'b0;
            end
            begin
                // Fill both registered observations before releasing the sink.
                while (!(voxel_valid && observation_valid && !observation_ready))
                    @(negedge aclk);
                repeat (6) @(negedge aclk);
                if (input_count != 8 || forwarded_count != 8 || voxel_count != 0)
                    $fatal(1, "Unexpected progress while both observation slots were full");
                // Drain observations while independently stopping AXI forwarding.
                m_axis_tready = 1'b0;
                voxel_ready = 1'b1;
                repeat (5) @(negedge aclk);
                if (input_count != 8 || voxel_count != 2)
                    $fatal(1, "AXI stall incorrectly affected observation draining");
                m_axis_tready = 1'b1;
                repeat (6) @(negedge aclk);
                voxel_ready = 1'b0;
                repeat (14) @(negedge aclk);
                voxel_ready = 1'b1;
            end
        join
        repeat (5) @(negedge aclk);
        if (input_count != 32 || forwarded_count != 32 || voxel_count != 8 ||
            voxel_valid !== 1'b0 || observation_valid !== 1'b0)
            $fatal(1, "Lost/duplicate pipeline data: input=%0d forwarded=%0d voxels=%0d",
                   input_count, forwarded_count, voxel_count);
        if (full_stalls < 6 || axis_stalls < 5 || voxel_stalls < 10 || overlap_count < 1)
            $fatal(1, "Insufficient stall or simultaneous acceptance coverage");
        $display("PASS: unpacker -> voxel: %0d observations, %0d AXI words; both sinks stalled",
                 voxel_count, forwarded_count);
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "Timeout waiting for unpacker -> voxel pipeline progress");
    end
endmodule
