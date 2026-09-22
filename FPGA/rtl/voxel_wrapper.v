module voxel_wrapper #(
    parameter integer X_MIN_MM = 0,
    parameter integer Y_MIN_MM = 0,
    parameter integer Z_MIN_MM = 0,
    parameter integer VOXEL_SIZE_MM = 500,
    parameter integer NX = 8,
    parameter integer NY = 8,
    parameter integer NZ = 4,
    parameter integer ADDR_WIDTH = (NX*NY*NZ > 1) ? $clog2(NX*NY*NZ) : 1
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET aresetn" *)
    input  wire                          aclk,

    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire                          aresetn,

    input  wire signed [31:0]            x_mm,
    input  wire signed [31:0]            y_mm,
    input  wire signed [31:0]            z_mm,
    input  wire signed [31:0]            rssi_dbm,
    input  wire                          observation_valid,
    output wire [ADDR_WIDTH-1:0]         voxel_address,
    output wire signed [31:0]            voxel_rssi_dbm,
    output wire                          voxel_valid,
    output wire                          out_of_bounds
);

    voxel #(
        .X_MIN_MM(X_MIN_MM),
        .Y_MIN_MM(Y_MIN_MM),
        .Z_MIN_MM(Z_MIN_MM),
        .VOXEL_SIZE_MM(VOXEL_SIZE_MM),
        .NX(NX),
        .NY(NY),
        .NZ(NZ),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) voxel_inst (
        .aclk(aclk),
        .aresetn(aresetn),
        .x_mm(x_mm),
        .y_mm(y_mm),
        .z_mm(z_mm),
        .rssi_dbm(rssi_dbm),
        .observation_valid(observation_valid),
        .voxel_address(voxel_address),
        .voxel_rssi_dbm(voxel_rssi_dbm),
        .voxel_valid(voxel_valid),
        .out_of_bounds(out_of_bounds)
    );

endmodule