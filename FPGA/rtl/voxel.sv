/*
Author: Sanat Konda
Updated: Sept 22, 2026

Purpose: Convert positions into signed voxel coordinates for a sparse map.
*/

module voxel #(
    parameter int X_ORIGIN_MM = 0,
    parameter int Y_ORIGIN_MM = 0,
    parameter int Z_ORIGIN_MM = 0,
    parameter int VOXEL_SIZE_MM = 500
) (
    input  logic               aclk,
    input  logic               aresetn,
    input  logic signed [31:0] x_mm,
    input  logic signed [31:0] y_mm,
    input  logic signed [31:0] z_mm,
    input  logic signed [31:0] rssi_dbm,
    input  logic               observation_valid,
    output logic               observation_ready,

    output logic signed [32:0] voxel_x,
    output logic signed [32:0] voxel_y,
    output logic signed [32:0] voxel_z,
    output logic signed [31:0] voxel_rssi_dbm,
    output logic               voxel_valid,
    input  logic               voxel_ready
);

    // This division is evaluated at elaboration, not by runtime hardware.
    localparam int SCALE_SHIFT = 32 + $clog2(VOXEL_SIZE_MM);
    localparam logic [32:0] RECIPROCAL = 33'(
        ((64'd1 << SCALE_SHIFT) + 64'(VOXEL_SIZE_MM) - 1) /
        64'(VOXEL_SIZE_MM)
    );

    logic signed [32:0] x_offset, y_offset, z_offset;
    logic signed [31:0] rssi_r;
    logic offset_valid;
    logic output_ready;

    function automatic logic signed [32:0] voxel_index(
        input logic signed [32:0] offset
    );
        logic [31:0] magnitude;
        logic [64:0] product;
        logic [32:0] quotient;

        // For negative offsets, use -offset-1, then -quotient-1: floor division.
        magnitude = offset[32] ? ~offset[31:0] : offset[31:0];
        product = magnitude * RECIPROCAL;
        quotient = 33'(product >> SCALE_SHIFT);
        return offset[32] ? $signed(~quotient) : $signed(quotient);
    endfunction

    assign output_ready = !voxel_valid || voxel_ready;
    assign observation_ready = aresetn && (!offset_valid || output_ready);

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            offset_valid <= 1'b0;
            voxel_valid  <= 1'b0;
        end else begin
            if (observation_ready)
                offset_valid <= observation_valid;

            if (output_ready)
                voxel_valid <= offset_valid;
        end

        // Data registers need no reset; their valid bits determine usability.
        if (observation_valid && observation_ready) begin
            x_offset <= 33'(x_mm) - 33'(X_ORIGIN_MM);
            y_offset <= 33'(y_mm) - 33'(Y_ORIGIN_MM);
            z_offset <= 33'(z_mm) - 33'(Z_ORIGIN_MM);
            rssi_r   <= rssi_dbm;
        end

        if (offset_valid && output_ready) begin
            voxel_x        <= voxel_index(x_offset);
            voxel_y        <= voxel_index(y_offset);
            voxel_z        <= voxel_index(z_offset);
            voxel_rssi_dbm <= rssi_r;
        end
    end

    // synthesis translate_off
    initial begin
        if (VOXEL_SIZE_MM <= 0)
            $fatal(1, "VOXEL_SIZE_MM must be positive");
    end
    // synthesis translate_on

endmodule
