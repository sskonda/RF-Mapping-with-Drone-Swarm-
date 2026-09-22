/*
Author: Sanat Konda
Date: Sept 21, 2026

Purpose: Map positions to voxel addresses, pass RSSI, and flag out-of-bounds observations.
*/

module voxel #(
    parameter int X_MIN_MM = 0,
    parameter int Y_MIN_MM = 0,
    parameter int Z_MIN_MM = 0,
    parameter int VOXEL_SIZE_MM = 500,
    parameter int NX = 8,
    parameter int NY = 8,
    parameter int NZ = 4,
    parameter int ADDR_WIDTH = (NX*NY*NZ > 1) ? $clog2(NX*NY*NZ) : 1
) (
    input  logic                         aclk,
    input  logic                         aresetn,
    input  logic signed [31:0]           x_mm,
    input  logic signed [31:0]           y_mm,
    input  logic signed [31:0]           z_mm,
    input  logic signed [31:0]           rssi_dbm,
    input  logic                         observation_valid,
    output logic [ADDR_WIDTH-1:0]        voxel_address,
    output logic signed [31:0]           voxel_rssi_dbm,
    output logic                         voxel_valid,
    output logic                         out_of_bounds
);

    localparam longint X_MAX_MM = longint'(X_MIN_MM) + longint'(NX)*VOXEL_SIZE_MM;
    localparam longint Y_MAX_MM = longint'(Y_MIN_MM) + longint'(NY)*VOXEL_SIZE_MM;
    localparam longint Z_MAX_MM = longint'(Z_MIN_MM) + longint'(NZ)*VOXEL_SIZE_MM;

    int unsigned vx, vy, vz;
    logic in_bounds;

    always_comb begin
        vx = 0;
        vy = 0;
        vz = 0;

        for (int i = 1; i < NX; i++)
            if (longint'(x_mm) >= longint'(X_MIN_MM) + longint'(i)*VOXEL_SIZE_MM)
                vx = i;

        for (int i = 1; i < NY; i++)
            if (longint'(y_mm) >= longint'(Y_MIN_MM) + longint'(i)*VOXEL_SIZE_MM)
                vy = i;

        for (int i = 1; i < NZ; i++)
            if (longint'(z_mm) >= longint'(Z_MIN_MM) + longint'(i)*VOXEL_SIZE_MM)
                vz = i;

        in_bounds = x_mm >= X_MIN_MM && longint'(x_mm) < X_MAX_MM &&
                    y_mm >= Y_MIN_MM && longint'(y_mm) < Y_MAX_MM &&
                    z_mm >= Z_MIN_MM && longint'(z_mm) < Z_MAX_MM;
    end

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            voxel_address  <= '0;
            voxel_rssi_dbm <= '0;
            voxel_valid    <= 1'b0;
            out_of_bounds  <= 1'b0;
        end else begin
            voxel_valid   <= observation_valid && in_bounds;
            out_of_bounds <= observation_valid && !in_bounds;

            if (observation_valid && in_bounds) begin
                voxel_address  <= ADDR_WIDTH'(vx + NX*vy + NX*NY*vz);
                voxel_rssi_dbm <= rssi_dbm;
            end
        end
    end

endmodule