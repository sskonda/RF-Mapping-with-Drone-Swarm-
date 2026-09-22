/*
Author: Sanat Konda
Date: Sept 21, 2026

Purpose: Extract x/y/z/RSSI observations while forwarding the AXI stream.
        AXI word 0 -> x
        AXI word 1 -> y
        AXI word 2 -> z
        AXI word 3 -> RSSI
*/

module rf_packet_unpacker #(
    parameter int DATA_WIDTH = 32
) (
    input logic aclk,
    input logic aresetn,

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
    output logic                         observation_valid
);

    typedef enum logic [1:0] {
        FIELD_X,
        FIELD_Y,
        FIELD_Z,
        FIELD_RSSI
    } field_t;

    field_t field;

    assign s_axis_tready = m_axis_tready;

    assign m_axis_tdata  = s_axis_tdata;
    assign m_axis_tvalid = s_axis_tvalid;
    assign m_axis_tlast  = s_axis_tlast;

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            field             <= FIELD_X;
            x_mm              <= '0;
            y_mm              <= '0;
            z_mm              <= '0;
            rssi_dbm          <= '0;
            observation_valid <= 1'b0;
        end else begin
            observation_valid <= 1'b0;

            if (s_axis_tvalid && s_axis_tready) begin
                case (field)
                    FIELD_X: begin
                        x_mm  <= $signed(s_axis_tdata);
                        field <= s_axis_tlast ? FIELD_X : FIELD_Y;
                    end

                    FIELD_Y: begin
                        y_mm  <= $signed(s_axis_tdata);
                        field <= s_axis_tlast ? FIELD_X : FIELD_Z;
                    end

                    FIELD_Z: begin
                        z_mm  <= $signed(s_axis_tdata);
                        field <= s_axis_tlast ? FIELD_X : FIELD_RSSI;
                    end

                    FIELD_RSSI: begin
                        rssi_dbm          <= $signed(s_axis_tdata);
                        observation_valid <= 1'b1;
                        field             <= FIELD_X;
                    end

                    default: begin
                        field <= FIELD_X;
                    end
                endcase
            end
        end
    end

endmodule