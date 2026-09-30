`timescale 1ns/1ps

// Check registered increment, wraparound, TLAST, ready/valid retention, and reset.
// From FPGA/tb with Vivado tools on PATH:
// xvlog -sv ../rtl/axis_passthrough.sv ../rtl/axis_passthrough_wrapper.v axis_passthrough_tb.sv
// xelab axis_passthrough_tb -s axis_passthrough_tb_sim --timescale 1ns/1ps
// xsim axis_passthrough_tb_sim -runall
module axis_passthrough_test_case #(
    parameter integer DATA_WIDTH = 32
) (
    input logic aclk,
    output logic done = 1'b0
);
    logic aresetn = 1'b0;
    logic [DATA_WIDTH-1:0] s_axis_tdata = '0, m_axis_tdata;
    logic s_axis_tvalid = 1'b0, s_axis_tready, s_axis_tlast = 1'b0;
    logic m_axis_tvalid, m_axis_tready = 1'b0, m_axis_tlast;

    axis_passthrough_wrapper #(.DATA_WIDTH(DATA_WIDTH)) dut (.*);

    logic [DATA_WIDTH-1:0] expected_data [0:255];
    logic expected_last [0:255];
    integer read_index = 0, write_index = 0;
    integer accepted_inputs = 0, accepted_outputs = 0, aborted = 0;
    integer stall_cycles = 0, simultaneous_transfers = 0, last_words = 0;
    logic previous_stall = 1'b0;
    logic [DATA_WIDTH:0] held_output;
    logic sender_done = 1'b0;

    // Sample handshakes before the DUT's nonblocking register updates.
    always @(posedge aclk) begin
        if (!aresetn) begin
            aborted = aborted + write_index - read_index;
            read_index = 0;
            write_index = 0;
            previous_stall = 1'b0;
        end else begin
            if (previous_stall &&
                (m_axis_tvalid !== 1'b1 ||
                 {m_axis_tdata, m_axis_tlast} !== held_output))
                $fatal(1, "Width %0d changed a blocked output", DATA_WIDTH);

            // Check output first: a newly accepted input cannot bypass the register.
            if (m_axis_tvalid) begin
                if (read_index >= write_index ||
                    m_axis_tdata !== expected_data[read_index] ||
                    m_axis_tlast !== expected_last[read_index])
                    $fatal(1, "Width %0d data/TLAST/latency mismatch", DATA_WIDTH);
                if (m_axis_tready) begin
                    read_index = read_index + 1;
                    accepted_outputs = accepted_outputs + 1;
                    if (m_axis_tlast) last_words = last_words + 1;
                end else begin
                    stall_cycles = stall_cycles + 1;
                    if (s_axis_tready !== 1'b0)
                        $fatal(1, "Width %0d failed to backpressure input", DATA_WIDTH);
                end
            end

            if (s_axis_tvalid && s_axis_tready) begin
                if (write_index >= 256) $fatal(1, "Test scoreboard overflow");
                expected_data[write_index] = s_axis_tdata + 1'b1;
                expected_last[write_index] = s_axis_tlast;
                write_index = write_index + 1;
                accepted_inputs = accepted_inputs + 1;
                if (m_axis_tvalid && m_axis_tready)
                    simultaneous_transfers = simultaneous_transfers + 1;
            end
            previous_stall = m_axis_tvalid && !m_axis_tready;
            held_output = {m_axis_tdata, m_axis_tlast};
        end
    end

    // Call on a falling edge; keep each word and TLAST stable until accepted.
    task automatic send_word(input logic [DATA_WIDTH-1:0] data, input logic last);
        begin
            s_axis_tdata = data;
            s_axis_tlast = last;
            s_axis_tvalid = 1'b1;
            @(posedge aclk);
            while (s_axis_tready !== 1'b1) @(posedge aclk);
            @(negedge aclk);
            s_axis_tvalid = 1'b0;
        end
    endtask

    task automatic reset_dut;
        begin
            aresetn = 1'b0;
            s_axis_tvalid = 1'b0;
            m_axis_tready = 1'b0;
            repeat (2) @(negedge aclk);
            if ({m_axis_tvalid, m_axis_tdata, m_axis_tlast} !== '0)
                $fatal(1, "Width %0d reset did not clear outputs", DATA_WIDTH);
            aresetn = 1'b1;
        end
    endtask

    task automatic drain;
        begin
            m_axis_tready = 1'b1;
            repeat (2) @(negedge aclk);
            if (read_index != write_index || m_axis_tvalid !== 1'b0)
                $fatal(1, "Width %0d lost output or failed to clear valid", DATA_WIDTH);
        end
    endtask

    initial begin
        @(negedge aclk);
        reset_dut();

        // An empty register accepts one word even with the receiver stopped.
        send_word(DATA_WIDTH'(41), 1'b0);
        fork
            send_word('1, 1'b1); // Maximum unsigned value wraps to zero.
            begin
                repeat (8) @(negedge aclk);
                m_axis_tready = 1'b1;
            end
        join
        send_word('0, 1'b0);
        send_word(DATA_WIDTH'(64'h8000000000000080), 1'b1);
        for (int i = 0; i < 12; i++)
            send_word(DATA_WIDTH'(i), i % 4 == 3);
        drain();

        // Vary producer gaps and receiver readiness independently.
        fork
            begin
                for (int i = 0; i < 64; i++) begin
                    repeat (i % 3) @(negedge aclk);
                    send_word(DATA_WIDTH'(64'hfedcba9876543210 ^ (64'(i) * 257)),
                              i % 7 == 6);
                end
                sender_done = 1'b1;
            end
            begin
                for (int cycle = 0; !sender_done; cycle++) begin
                    m_axis_tready = ((cycle % 7) >= 3);
                    @(negedge aclk);
                end
                m_axis_tready = 1'b1;
            end
        join
        drain();

        // Reset discards exactly one blocked output; fresh traffic must recover.
        m_axis_tready = 1'b0;
        send_word(DATA_WIDTH'(123), 1'b1);
        repeat (3) @(negedge aclk);
        reset_dut();
        m_axis_tready = 1'b1;
        send_word(DATA_WIDTH'(99), 1'b1);
        drain();

        if (accepted_inputs != accepted_outputs + aborted || aborted != 1 ||
            accepted_outputs != 81 || stall_cycles < 11 ||
            simultaneous_transfers < 12 || last_words < 6)
            $fatal(1, "Width %0d wrong totals or missing coverage", DATA_WIDTH);
        $display("PASS axis width %0d: in=%0d out=%0d aborted=%0d stalls=%0d overlap=%0d",
                 DATA_WIDTH, accepted_inputs, accepted_outputs, aborted,
                 stall_cycles, simultaneous_transfers);
        done = 1'b1;
    end
endmodule

module axis_passthrough_tb;
    logic aclk = 1'b0;
    always #5 aclk = ~aclk;
    wire [2:0] done;

    axis_passthrough_test_case #(.DATA_WIDTH(8)) byte_words (aclk, done[0]);
    axis_passthrough_test_case #(.DATA_WIDTH(32)) default_words (aclk, done[1]);
    axis_passthrough_test_case #(.DATA_WIDTH(64)) wide_words (aclk, done[2]);

    initial begin
        wait (&done);
        $display("PASS: all axis passthrough configurations");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "Timeout waiting for axis passthrough progress");
    end
endmodule
