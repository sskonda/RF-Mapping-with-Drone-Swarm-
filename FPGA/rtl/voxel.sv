/*
Author: Sanat Konda
Updated: Sept 23, 2026

Purpose: Convert positions into signed voxel coordinates for a sparse map.
Four elastic stages: normalize, partial products, partial sums, output.
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

    localparam int ORIGIN_MM [3] = '{X_ORIGIN_MM, Y_ORIGIN_MM, Z_ORIGIN_MM};
    logic signed [31:0] position [3];
    logic signed [32:0] coordinate [3];
    logic signed [31:0] rssi_pipe [4];
    logic [3:0] stage_valid, stage_ready;

    assign position[0] = x_mm;
    assign position[1] = y_mm;
    assign position[2] = z_mm;
    assign voxel_x = coordinate[0];
    assign voxel_y = coordinate[1];
    assign voxel_z = coordinate[2];
    assign voxel_rssi_dbm = rssi_pipe[3];
    assign voxel_valid = stage_valid[3];
    assign observation_ready = aresetn && stage_ready[0];

    assign stage_ready[3] = !stage_valid[3] || voxel_ready;
    for (genvar stage = 0; stage < 3; stage++) begin : g_ready
        assign stage_ready[stage] = !stage_valid[stage] || stage_ready[stage+1];
    end

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            stage_valid <= '0;
        end else begin
            if (stage_ready[0])
                stage_valid[0] <= observation_valid;
            for (int stage = 1; stage < 4; stage++)
                if (stage_ready[stage])
                    stage_valid[stage] <= stage_valid[stage-1];
        end

        // Payload registers need no reset; valid bits determine usability.
        if (observation_valid && observation_ready)
            rssi_pipe[0] <= rssi_dbm;
        for (int stage = 1; stage < 4; stage++)
            if (stage_valid[stage-1] && stage_ready[stage])
                rssi_pipe[stage] <= rssi_pipe[stage-1];
    end

    for (genvar axis = 0; axis < 3; axis++) begin : g_axis
        logic signed [32:0] offset;
        logic [31:0] magnitude;
        logic [2:0] negative;
        (* use_dsp = "yes" *) logic [31:0] product_ll, product_hl;
        (* use_dsp = "yes" *) logic [32:0] product_lh, product_hh;
        logic [48:0] sum_lo, sum_hi;
        logic [64:0] product;
        logic [32:0] quotient;

        assign offset = 33'(position[axis]) - 33'(ORIGIN_MM[axis]);
        assign product = {16'b0, sum_lo} + {sum_hi, 16'b0};
        assign quotient = 33'(product >> SCALE_SHIFT);

        always_ff @(posedge aclk) begin
            // Stage 0: negative offsets use -offset-1 for floor division.
            if (observation_valid && observation_ready) begin
                magnitude <= offset[32] ? ~offset[31:0] : offset[31:0];
                negative[0] <= offset[32];
            end

            // Stage 1: each 16x16 or 16x17 product fits one DSP48E1.
            if (stage_valid[0] && stage_ready[1]) begin
                product_ll <= magnitude[15:0]  * RECIPROCAL[15:0];
                product_lh <= magnitude[15:0]  * RECIPROCAL[32:16];
                product_hl <= magnitude[31:16] * RECIPROCAL[15:0];
                product_hh <= magnitude[31:16] * RECIPROCAL[32:16];
                negative[1] <= negative[0];
            end

            // Stage 2: reconstruct each 16x33 half-product independently.
            if (stage_valid[1] && stage_ready[2]) begin
                sum_lo <= {17'b0, product_ll} + {product_lh, 16'b0};
                sum_hi <= {17'b0, product_hl} + {product_hh, 16'b0};
                negative[2] <= negative[1];
            end

            // Stage 3: combine halves, scale, and restore the signed floor.
            if (stage_valid[2] && stage_ready[3])
                coordinate[axis] <= negative[2] ? $signed(~quotient) :
                                                 $signed(quotient);
        end
    end

    // synthesis translate_off
    initial begin
        if (VOXEL_SIZE_MM <= 0)
            $fatal(1, "VOXEL_SIZE_MM must be positive");
    end
    // synthesis translate_on

endmodule
