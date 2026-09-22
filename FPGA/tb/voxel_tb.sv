`timescale 1ns/1ps

// Check signed voxel boundaries, arbitrary origins, and ready/valid retention.
// From FPGA/tb with Vivado tools on PATH:
// xvlog -sv ../rtl/voxel.sv ../rtl/voxel_wrapper.v voxel_tb.sv
// xelab voxel_tb -s voxel_tb_sim --timescale 1ns/1ps
// xsim voxel_tb_sim -runall
module voxel_test_case #(
    parameter integer CASE_ID = 0,
    parameter integer X_ORIGIN_MM = 0,
    parameter integer Y_ORIGIN_MM = 0,
    parameter integer Z_ORIGIN_MM = 0,
    parameter integer VOXEL_SIZE_MM = 500
) (
    input logic aclk,
    output logic done = 1'b0
);
    logic aresetn = 1'b0;
    logic signed [31:0] x_mm = 0, y_mm = 0, z_mm = 0, rssi_dbm = 0;
    logic observation_valid = 1'b0, observation_ready;
    logic signed [32:0] vx, vy, vz;
    logic signed [31:0] voxel_rssi_dbm;
    logic voxel_valid, voxel_ready = 1'b0;

    voxel_wrapper #(
        .X_ORIGIN_MM(X_ORIGIN_MM), .Y_ORIGIN_MM(Y_ORIGIN_MM),
        .Z_ORIGIN_MM(Z_ORIGIN_MM), .VOXEL_SIZE_MM(VOXEL_SIZE_MM)
    ) dut (.*);

    integer expected_x [0:127], expected_y [0:127], expected_z [0:127];
    integer expected_rssi [0:127];
    integer read_index = 0, write_index = 0;
    integer accepted_inputs = 0, accepted_outputs = 0;
    integer stall_cycles = 0, simultaneous_transfers = 0;
    logic previous_stall = 1'b0;
    logic [130:0] held_output;
    logic sender_done = 1'b0;

    // Independently verify that the reported voxel contains the input position:
    // origin + index*size <= position < origin + (index+1)*size.
    // This catches truncation toward zero without duplicating the DUT division.
    task automatic check_coordinate(
        input longint coordinate, input integer position,
        input integer origin, input string axis_name
    );
        longint lower_bound;
        begin
            lower_bound = longint'(origin) + coordinate * VOXEL_SIZE_MM;
            if (longint'(position) < lower_bound ||
                longint'(position) >= lower_bound + VOXEL_SIZE_MM)
                $fatal(1, "Case %0d %s: position %0d is not in voxel %0d",
                       CASE_ID, axis_name, position, coordinate);
        end
    endtask

    // Sample handshakes before the DUT's nonblocking register updates.
    always @(posedge aclk) begin
        if (!aresetn) begin
            read_index = 0;
            write_index = 0;
            previous_stall = 1'b0;
            if (observation_ready !== 1'b0)
                $fatal(1, "Case %0d accepted input during reset", CASE_ID);
        end else begin
            if (previous_stall &&
                (voxel_valid !== 1'b1 ||
                 {vx, vy, vz, voxel_rssi_dbm} !== held_output))
                $fatal(1, "Case %0d changed a blocked output", CASE_ID);

            if (voxel_valid) begin
                if (read_index >= write_index)
                    $fatal(1, "Case %0d produced an unexpected output", CASE_ID);
                if ($isunknown({vx, vy, vz, voxel_rssi_dbm}))
                    $fatal(1, "Case %0d produced unknown output data", CASE_ID);
                check_coordinate(vx, expected_x[read_index], X_ORIGIN_MM, "X");
                check_coordinate(vy, expected_y[read_index], Y_ORIGIN_MM, "Y");
                check_coordinate(vz, expected_z[read_index], Z_ORIGIN_MM, "Z");
                if (voxel_rssi_dbm !== expected_rssi[read_index])
                    $fatal(1, "Case %0d changed RSSI or reordered outputs", CASE_ID);
                if (voxel_ready) begin
                    read_index = read_index + 1;
                    accepted_outputs = accepted_outputs + 1;
                end else begin
                    stall_cycles = stall_cycles + 1;
                    if (observation_ready !== 1'b0)
                        $fatal(1, "Case %0d failed to backpressure its input", CASE_ID);
                end
            end

            if (observation_valid && observation_ready) begin
                if (write_index >= 128)
                    $fatal(1, "Test scoreboard overflow");
                expected_x[write_index] = x_mm;
                expected_y[write_index] = y_mm;
                expected_z[write_index] = z_mm;
                expected_rssi[write_index] = rssi_dbm;
                write_index = write_index + 1;
                accepted_inputs = accepted_inputs + 1;
                if (voxel_valid && voxel_ready)
                    simultaneous_transfers = simultaneous_transfers + 1;
            end
            previous_stall = voxel_valid && !voxel_ready;
            held_output = {vx, vy, vz, voxel_rssi_dbm};
        end
    end

    // Called on falling edges; hold the entire observation until accepted.
    task automatic send_observation(
        input integer x, input integer y, input integer z, input integer rssi
    );
        begin
            x_mm = x; y_mm = y; z_mm = z; rssi_dbm = rssi;
            observation_valid = 1'b1;
            @(posedge aclk);
            while (observation_ready !== 1'b1) @(posedge aclk);
            @(negedge aclk);
            observation_valid = 1'b0;
        end
    endtask

    task automatic reset_dut;
        begin
            aresetn = 1'b0;
            observation_valid = 1'b0;
            voxel_ready = 1'b0;
            repeat (2) @(negedge aclk);
            if (voxel_valid !== 1'b0 ||
                {vx, vy, vz, voxel_rssi_dbm} !== 131'b0)
                $fatal(1, "Case %0d reset did not clear outputs", CASE_ID);
            aresetn = 1'b1;
        end
    endtask

    task automatic drain;
        begin
            voxel_ready = 1'b1;
            repeat (2) @(negedge aclk);
            if (read_index != write_index || voxel_valid !== 1'b0)
                $fatal(1, "Case %0d lost an output or failed to clear valid", CASE_ID);
        end
    endtask

    initial begin
        @(negedge aclk);
        reset_dut();

        // Fill the output slot, then hold a second input through a long stall.
        send_observation(-1, -500, -501, -61);
        fork
            send_observation(0, 499, 500, -62);
            begin
                repeat (8) @(negedge aclk);
                voxel_ready = 1'b1;
            end
        join

        // Consecutive observations must consume and replace the output slot.
        send_observation(501, 1000, -1000, -63);
        send_observation(1000000, -1000000, 300000, -64);
        send_observation(32'sh7fffffff, 32'sh80000000, 32'sh7fffffff, -65);
        send_observation(32'sh80000000, 32'sh7fffffff, 32'sh80000000, -66);
        send_observation(X_ORIGIN_MM, Y_ORIGIN_MM, Z_ORIGIN_MM, -67);
        if (VOXEL_SIZE_MM > 1) begin
            // Parameters for these cases leave room for boundary arithmetic.
            send_observation(X_ORIGIN_MM - 1, Y_ORIGIN_MM - VOXEL_SIZE_MM,
                             Z_ORIGIN_MM - VOXEL_SIZE_MM - 1, -68);
            send_observation(X_ORIGIN_MM + VOXEL_SIZE_MM - 1,
                             Y_ORIGIN_MM + VOXEL_SIZE_MM,
                             Z_ORIGIN_MM + VOXEL_SIZE_MM + 1, -69);
        end
        drain();

        // Vary producer gaps and receiver readiness independently.
        fork
            begin
                for (int i = 0; i < 24; i++) begin
                    repeat (i % 3) @(negedge aclk);
                    send_observation(i*113 - 1500, 750 - i*97, i*503 - 5000, -70-i);
                end
                sender_done = 1'b1;
            end
            begin
                for (int cycle = 0; !sender_done; cycle++) begin
                    voxel_ready = ((cycle % 7) >= 3);
                    @(negedge aclk);
                end
                voxel_ready = 1'b1;
            end
        join
        drain();

        // Reset deliberately discards one complete, blocked output.
        voxel_ready = 1'b0;
        send_observation(123, -456, 789, -100);
        repeat (3) @(negedge aclk);
        reset_dut();
        voxel_ready = 1'b1;
        send_observation(-999999, 999999, -1, -101);
        drain();

        if (accepted_inputs != accepted_outputs + 1 ||
            stall_cycles < 11 || simultaneous_transfers < 4)
            $fatal(1, "Case %0d wrong totals/coverage: in=%0d out=%0d stalls=%0d overlap=%0d",
                   CASE_ID, accepted_inputs, accepted_outputs,
                   stall_cycles, simultaneous_transfers);
        $display("PASS voxel case %0d: %0d accepted outputs; signed coordinates, stalls, reset",
                 CASE_ID, accepted_outputs);
        done = 1'b1;
    end
endmodule

module voxel_tb;
    logic aclk = 1'b0;
    always #5 aclk = ~aclk;
    wire [2:0] done;

    voxel_test_case #(.CASE_ID(0)) default_grid (aclk, done[0]);
    voxel_test_case #(
        .CASE_ID(1), .X_ORIGIN_MM(1250), .Y_ORIGIN_MM(-750), .Z_ORIGIN_MM(250)
    ) shifted_origin (aclk, done[1]);
    voxel_test_case #(
        .CASE_ID(2), .X_ORIGIN_MM(32'sh80000000),
        .Y_ORIGIN_MM(32'sh7fffffff), .Z_ORIGIN_MM(32'sh80000000), .VOXEL_SIZE_MM(1)
    ) full_signed_range (aclk, done[2]);

    initial begin
        wait (&done);
        $display("PASS: all voxel cases completed");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "Timeout waiting for voxel progress");
    end
endmodule
