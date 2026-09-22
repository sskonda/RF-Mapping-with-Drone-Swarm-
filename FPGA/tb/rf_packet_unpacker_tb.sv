`timescale 1ns/1ps

// Exercise observation retention, AXI backpressure, packet boundaries, and reset.
// From FPGA/tb with Vivado tools on PATH:
// xvlog -sv ../rtl/rf_packet_unpacker.sv ../rtl/rf_packet_unpacker_wrapper.v rf_packet_unpacker_tb.sv
// xelab rf_packet_unpacker_tb -s rf_packet_unpacker_tb_sim --timescale 1ns/1ps
// xsim rf_packet_unpacker_tb_sim -runall
module rf_packet_unpacker_tb;
    logic aclk = 1'b0;
    always #5 aclk = ~aclk;

    logic aresetn;
    logic [31:0] s_axis_tdata;
    logic s_axis_tvalid, s_axis_tready, s_axis_tlast;
    logic [31:0] m_axis_tdata;
    logic m_axis_tvalid, m_axis_tready, m_axis_tlast;
    logic signed [31:0] x_mm, y_mm, z_mm, rssi_dbm;
    logic observation_valid, observation_ready;

    rf_packet_unpacker_wrapper dut (.*);

    integer expected_x [0:63];
    integer expected_y [0:63];
    integer expected_z [0:63];
    integer expected_rssi [0:63];
    integer expected_read = 0;
    integer expected_write = 0;
    integer input_words = 0;
    integer output_words = 0;
    integer accepted_observations = 0;
    integer simultaneous_transfers = 0;
    integer observation_stall_cycles = 0;
    integer axis_stall_cycles = 0;

    logic previous_observation_stall = 1'b0;
    logic previous_axis_stall = 1'b0;
    logic [127:0] held_observation;
    logic [31:0] held_axis_data;
    logic held_axis_last;

    // Check the values visible to receivers at the sampling edge, before NBA updates.
    always @(posedge aclk) begin
        if (!aresetn) begin
            previous_observation_stall = 1'b0;
            previous_axis_stall = 1'b0;
            if (s_axis_tready !== 1'b0 || m_axis_tvalid !== 1'b0)
                $fatal(1, "AXI must not transfer while reset is asserted");
        end else begin
            if ((s_axis_tvalid && s_axis_tready) !==
                (m_axis_tvalid && m_axis_tready))
                $fatal(1, "Input and forwarded AXI transfers diverged");

            if (previous_axis_stall &&
                (m_axis_tvalid !== 1'b1 || m_axis_tdata !== held_axis_data ||
                 m_axis_tlast !== held_axis_last))
                $fatal(1, "Forwarded AXI word changed or valid dropped during a stall");

            if (previous_observation_stall &&
                (observation_valid !== 1'b1 ||
                 {x_mm, y_mm, z_mm, rssi_dbm} !== held_observation))
                $fatal(1, "Pending observation changed or valid dropped before acceptance");

            if (observation_valid && !observation_ready) begin
                observation_stall_cycles = observation_stall_cycles + 1;
                if (s_axis_tready !== 1'b0 || m_axis_tvalid !== 1'b0)
                    $fatal(1, "Pending observation did not block both AXI interfaces");
            end

            if (s_axis_tvalid && s_axis_tready)
                input_words = input_words + 1;
            if (m_axis_tvalid && m_axis_tready) begin
                output_words = output_words + 1;
                if (m_axis_tdata !== s_axis_tdata || m_axis_tlast !== s_axis_tlast)
                    $fatal(1, "AXI forwarding modified data or TLAST");
            end

            if (observation_valid) begin
                if (expected_read >= expected_write)
                    $fatal(1, "Unexpected or duplicate observation");
                if (x_mm !== expected_x[expected_read] ||
                    y_mm !== expected_y[expected_read] ||
                    z_mm !== expected_z[expected_read] ||
                    rssi_dbm !== expected_rssi[expected_read])
                    $fatal(1, "Observation mismatch: got (%0d, %0d, %0d, %0d)",
                           x_mm, y_mm, z_mm, rssi_dbm);
                if (observation_ready) begin
                    expected_read = expected_read + 1;
                    accepted_observations = accepted_observations + 1;
                    if (s_axis_tvalid && s_axis_tready)
                        simultaneous_transfers = simultaneous_transfers + 1;
                end
            end

            previous_observation_stall = observation_valid && !observation_ready;
            held_observation = {x_mm, y_mm, z_mm, rssi_dbm};
            previous_axis_stall = m_axis_tvalid && !m_axis_tready;
            held_axis_data = m_axis_tdata;
            held_axis_last = m_axis_tlast;
            if (previous_axis_stall)
                axis_stall_cycles = axis_stall_cycles + 1;
        end
    end

    task automatic expect_observation(
        input integer x, input integer y, input integer z, input integer rssi
    );
        begin
            if (expected_write >= 64)
                $fatal(1, "Expected observation queue overflow");
            expected_x[expected_write] = x;
            expected_y[expected_write] = y;
            expected_z[expected_write] = z;
            expected_rssi[expected_write] = rssi;
            expected_write = expected_write + 1;
        end
    endtask

    // Call on a falling edge; keep the source word stable until its handshake.
    // Returning on the next falling edge allows consecutive calls without bubbles.
    task automatic send_word(input integer data, input logic last);
        begin
            s_axis_tdata = data;
            s_axis_tlast = last;
            s_axis_tvalid = 1'b1;
            @(posedge aclk);
            while (s_axis_tready !== 1'b1)
                @(posedge aclk);
            @(negedge aclk);
            s_axis_tvalid = 1'b0;
        end
    endtask

    task automatic send_packet(
        input integer x, input integer y, input integer z, input integer rssi,
        input logic last
    );
        begin
            expect_observation(x, y, z, rssi);
            send_word(x, 1'b0);
            send_word(y, 1'b0);
            send_word(z, 1'b0);
            send_word(rssi, last);
        end
    endtask

    task automatic reset_dut;
        begin
            aresetn = 1'b0;
            s_axis_tvalid = 1'b0;
            observation_ready = 1'b0;
            m_axis_tready = 1'b1;
            // Reset intentionally discards pending/partial observations.
            expected_read = 0;
            expected_write = 0;
            repeat (2) @(negedge aclk);
            if (observation_valid !== 1'b0 ||
                {x_mm, y_mm, z_mm, rssi_dbm} !== 128'b0)
                $fatal(1, "Reset did not clear observation outputs");
            aresetn = 1'b1;
        end
    endtask

    task automatic drain_observations;
        begin
            observation_ready = 1'b1;
            repeat (2) @(negedge aclk);
            if (expected_read != expected_write || observation_valid !== 1'b0)
                $fatal(1, "Observation missing or valid not cleared after acceptance");
        end
    endtask

    integer words_before_stall;
    initial begin
        aresetn = 1'b0;
        s_axis_tdata = '0;
        s_axis_tvalid = 1'b0;
        s_axis_tlast = 1'b0;
        m_axis_tready = 1'b1;
        observation_ready = 1'b0;
        @(negedge aclk);
        reset_dut();

        // A ready AXI receiver must not see the waiting next packet repeatedly.
        send_packet(-1000, 2000, -500, -65, 1'b1);
        words_before_stall = input_words;
        fork
            send_packet(101, 202, 303, -77, 1'b1);
            begin
                repeat (8) @(negedge aclk);
                if (input_words != words_before_stall ||
                    output_words != words_before_stall || accepted_observations != 0)
                    $fatal(1, "A transfer escaped the observation stall");
                observation_ready = 1'b1;
            end
        join
        drain_observations();

        // Independent AXI backpressure in the middle of a packet.
        expect_observation(400, -500, 600, -88);
        send_word(400, 1'b0);
        m_axis_tready = 1'b0;
        fork
            send_word(-500, 1'b0);
            begin
                repeat (5) @(negedge aclk);
                m_axis_tready = 1'b1;
            end
        join
        send_word(600, 1'b0);
        send_word(-88, 1'b1);
        drain_observations();

        // Consume an observation while the next X is AXI-stalled. Dropping
        // observation_ready afterwards must not revoke that already offered X.
        observation_ready = 1'b0;
        send_packet(700, 800, 900, -99, 1'b1);
        expect_observation(-1, -2, -3, -100);
        m_axis_tready = 1'b0;
        fork
            send_word(-1, 1'b0);
            begin
                repeat (2) @(negedge aclk);
                observation_ready = 1'b1;
                @(negedge aclk);
                observation_ready = 1'b0;
                repeat (3) @(negedge aclk);
                if (observation_valid !== 1'b0 || m_axis_tvalid !== 1'b1)
                    $fatal(1, "Consumed observation continued blocking AXI");
                m_axis_tready = 1'b1;
            end
        join
        send_word(-2, 1'b0);
        send_word(-3, 1'b0);
        send_word(-100, 1'b1);
        drain_observations();

        // Continuous traffic, signed extremes, and a fourth word without TLAST.
        send_packet(32'sh80000000, 32'sh7fffffff, 0, -1, 1'b1);
        send_packet(11, 22, 33, -44, 1'b0);
        send_packet(55, 66, 77, -88, 1'b1);
        drain_observations();

        // Reset a complete, unaccepted observation, then accept a fresh packet.
        observation_ready = 1'b0;
        send_packet(123, 456, 789, -12, 1'b1);
        repeat (3) @(negedge aclk);
        reset_dut();
        observation_ready = 1'b1;
        send_packet(321, 654, 987, -21, 1'b1);
        drain_observations();

        // Reset after X/Y: the first post-reset word must again mean X.
        send_word(111, 1'b0);
        send_word(222, 1'b0);
        reset_dut();
        observation_ready = 1'b1;
        send_packet(333, 444, 555, -66, 1'b1);
        drain_observations();

        // TLAST at X, Y, or Z must discard the partial tuple and restart at X.
        send_word(901, 1'b1);
        send_word(902, 1'b0);
        send_word(903, 1'b1);
        send_word(904, 1'b0);
        send_word(905, 1'b0);
        send_word(906, 1'b1);
        send_packet(10, 20, 30, -40, 1'b1);
        drain_observations();

        if (accepted_observations != 11 || input_words != 56 || output_words != 56)
            $fatal(1, "Wrong totals: observations=%0d input=%0d output=%0d",
                   accepted_observations, input_words, output_words);
        if (simultaneous_transfers < 3 || observation_stall_cycles < 10 ||
            axis_stall_cycles < 5)
            $fatal(1, "Required backpressure/overlap coverage was not exercised");
        $display("PASS: %0d observations accepted, %0d AXI words forwarded; reset drops pending data",
                 accepted_observations, output_words);
        $finish;
    end

    initial begin
        #100000;
        $fatal(1, "Timeout waiting for rf_packet_unpacker progress");
    end
endmodule
