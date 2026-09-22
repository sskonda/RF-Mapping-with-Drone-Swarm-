/*
Author: Sanat Konda
Updated: Sept 22, 2026

Purpose: Forward AXI words unchanged and extract x/y/z/RSSI observations.
         Hold each completed observation until observation_ready is high.
*/

module rf_packet_unpacker #(
    parameter int DATA_WIDTH = 32
) (
    input  logic                  aclk,
    input  logic                  aresetn,

    input  logic [DATA_WIDTH-1:0] s_axis_tdata,
    input  logic                  s_axis_tvalid,
    output logic                  s_axis_tready,
    input  logic                  s_axis_tlast,

    output logic [DATA_WIDTH-1:0] m_axis_tdata,
    output logic                  m_axis_tvalid,
    input  logic                  m_axis_tready,
    output logic                  m_axis_tlast,

    output logic signed [DATA_WIDTH-1:0] x_mm,
    output logic signed [DATA_WIDTH-1:0] y_mm,
    output logic signed [DATA_WIDTH-1:0] z_mm,
    output logic signed [DATA_WIDTH-1:0] rssi_dbm,
    output logic                         observation_valid,
    input  logic                         observation_ready
);

    typedef enum logic [1:0] {
        FIELD_X,
        FIELD_Y,
        FIELD_Z,
        FIELD_RSSI
    } field_t;

    field_t field;
    logic signed [DATA_WIDTH-1:0] x_pending, y_pending, z_pending;
    logic stream_enable;
    logic transfer;

    // Only the fourth word waits for space in the observation register.
    assign stream_enable = aresetn &&
        (field != FIELD_RSSI || !observation_valid || observation_ready);

    assign s_axis_tready = m_axis_tready && stream_enable;
    assign m_axis_tvalid = s_axis_tvalid && stream_enable;
    assign m_axis_tdata  = s_axis_tdata;
    assign m_axis_tlast  = s_axis_tlast;
    assign transfer     = s_axis_tvalid && s_axis_tready;

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            field             <= FIELD_X;
            observation_valid <= 1'b0;
        end else begin
            if (observation_ready)
                observation_valid <= 1'b0;

            if (transfer) begin
                if (s_axis_tlast || field == FIELD_RSSI)
                    field <= FIELD_X;
                else
                    field <= field_t'(field + 2'd1);

                if (field == FIELD_RSSI)
                    observation_valid <= 1'b1;
            end
        end

        if (transfer) begin
            case (field)
                FIELD_X: x_pending <= $signed(s_axis_tdata);
                FIELD_Y: y_pending <= $signed(s_axis_tdata);
                FIELD_Z: z_pending <= $signed(s_axis_tdata);
                FIELD_RSSI: begin
                    x_mm     <= x_pending;
                    y_mm     <= y_pending;
                    z_mm     <= z_pending;
                    rssi_dbm <= $signed(s_axis_tdata);
                end
            endcase
        end
    end

endmodule
