/*
Author: Sanat Konda
Updated: Oct 5, 2026

Purpose: Forward AXI words and extract seven-word RF observations with metadata.
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
    output logic [31:0] observation_drone_id,
    output logic [63:0] observation_timestamp_us,
    output logic                         observation_valid,
    input  logic                         observation_ready
);

    typedef enum logic [2:0] {
        FIELD_X, FIELD_Y, FIELD_Z, FIELD_RSSI, FIELD_DRONE,
        FIELD_TIME_LO, FIELD_TIME_HI, DISCARD
    } field_t;

    field_t field;
    logic signed [31:0] x_pending, y_pending, z_pending, rssi_pending;
    logic [31:0] drone_pending, time_low_pending;
    logic stream_enable, transfer;

    // Only the last word waits for room in the completed observation register.
    assign stream_enable = aresetn &&
        (field != FIELD_TIME_HI || !observation_valid || observation_ready);
    assign s_axis_tready = m_axis_tready && stream_enable;
    assign m_axis_tvalid = s_axis_tvalid && stream_enable;
    assign m_axis_tdata = s_axis_tdata;
    assign m_axis_tlast = s_axis_tlast;
    assign transfer = s_axis_tvalid && s_axis_tready;

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            field <= FIELD_X;
            observation_valid <= 1'b0;
        end else begin
            if (observation_ready)
                observation_valid <= 1'b0;
            if (transfer) begin
                // Early TLAST drops a short packet. A missing final TLAST
                // enters DISCARD until TLAST restores the packet boundary.
                if (s_axis_tlast)
                    field <= FIELD_X;
                else if (field != DISCARD)
                    field <= field_t'(field + 3'd1);

                if (field == FIELD_TIME_HI && s_axis_tlast)
                    observation_valid <= 1'b1;
            end
        end

        // No payload reset: observation_valid guards the complete record.
        if (transfer) begin
            case (field)
                FIELD_X: x_pending <= $signed(s_axis_tdata);
                FIELD_Y: y_pending <= $signed(s_axis_tdata);
                FIELD_Z: z_pending <= $signed(s_axis_tdata);
                FIELD_RSSI: rssi_pending <= $signed(s_axis_tdata);
                FIELD_DRONE: drone_pending <= s_axis_tdata;
                FIELD_TIME_LO: time_low_pending <= s_axis_tdata;
                FIELD_TIME_HI: begin
                    if (s_axis_tlast) begin
                        x_mm <= x_pending;
                        y_mm <= y_pending;
                        z_mm <= z_pending;
                        rssi_dbm <= rssi_pending;
                        observation_drone_id <= drone_pending;
                        observation_timestamp_us <= {s_axis_tdata, time_low_pending};
                    end
                end
                default: begin end
            endcase
        end
    end

    // synthesis translate_off
    initial begin
        if (DATA_WIDTH != 32)
            $fatal(1, "Metadata packet format requires DATA_WIDTH=32");
    end
    // synthesis translate_on

endmodule
