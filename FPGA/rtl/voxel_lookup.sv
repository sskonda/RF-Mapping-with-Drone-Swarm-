/*
Author: Sanat Konda
Updated: Sept 24, 2026

Purpose: Assign stable storage slots to signed voxel coordinates.
A BRAM hash table uses linear probing and valid/ready flow control.
*/

module voxel_lookup #(
    parameter int MAX_VOXELS = 1024,
    parameter int TABLE_SIZE = 2048
) (
    input  logic               aclk,
    input  logic               aresetn,
    input  logic signed [32:0] voxel_x,
    input  logic signed [32:0] voxel_y,
    input  logic signed [32:0] voxel_z,
    input  logic signed [31:0] voxel_rssi_dbm,
    input  logic               voxel_valid,
    output logic               voxel_ready,

    output logic [((MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1)-1:0] lookup_slot,
    output logic signed [31:0] lookup_rssi_dbm,
    output logic               lookup_new,
    output logic               lookup_rejected,
    output logic               lookup_valid,
    input  logic               lookup_ready,

    output logic               init_done,
    output logic               map_full,
    output logic [$clog2(MAX_VOXELS+1)-1:0] used_voxels
);

    localparam int ADDR_WIDTH = $clog2(TABLE_SIZE);
    localparam int SLOT_WIDTH = (MAX_VOXELS > 1) ? $clog2(MAX_VOXELS) : 1;
    localparam int COUNT_WIDTH = $clog2(MAX_VOXELS+1);

    typedef struct packed {
        logic                  valid;
        logic [98:0]           key;
        logic [SLOT_WIDTH-1:0] slot;
    } entry_t;

    typedef enum logic [1:0] {CLEAR, IDLE, PROBE} state_t;
    state_t state;

    (* ram_style = "block" *) entry_t table_mem [TABLE_SIZE];
    entry_t read_entry, write_entry;
    logic [98:0] request_key;
    logic [ADDR_WIDTH-1:0] address, attempts, read_address;
    logic read_enable, write_enable, accept, match, advance, allocate;

    // Build constant parity masks at elaboration using a CRC polynomial.
    // Runtime hardware is an XOR reduction per address bit, with no multiplier.
    function automatic logic [98:0] hash_mask(input logic [4:0] address_bit);
        logic [31:0] column;
        column = 32'h9e3779b9;
        for (int bit_index = 0; bit_index < 99; bit_index++) begin
            hash_mask[bit_index] = column[address_bit];
            column = {column[30:0], 1'b0} ^
                     ({32{column[31]}} & 32'h04c11db7);
        end
    endfunction

    function automatic logic [ADDR_WIDTH-1:0] hash_key(input logic [98:0] key);
        for (int bit_index = 0; bit_index < ADDR_WIDTH; bit_index++)
            hash_key[bit_index] = ^(key & hash_mask(5'(bit_index)));
    endfunction

    assign init_done = aresetn && (state != CLEAR);
    assign map_full = (used_voxels == COUNT_WIDTH'(MAX_VOXELS));
    assign voxel_ready = aresetn && (state == IDLE) &&
                         (!lookup_valid || lookup_ready);
    assign accept = voxel_valid && voxel_ready;
    assign match = read_entry.valid && (read_entry.key == request_key);
    assign advance = (state == PROBE) && read_entry.valid && !match &&
                     (attempts != ADDR_WIDTH'(TABLE_SIZE-1));
    assign allocate = (state == PROBE) && !read_entry.valid && !map_full;

    assign read_enable = aresetn && (accept || advance);
    assign read_address = accept ? hash_key({voxel_x, voxel_y, voxel_z}) :
                                   address + 1'b1;
    assign write_enable = aresetn && ((state == CLEAR) || allocate);
    assign write_entry = (state == CLEAR) ? '0 :
                         {1'b1, request_key, SLOT_WIDTH'(used_voxels)};

    // Synchronous RAM ports; reset clears one entry per cycle through this port.
    // Reads and writes never occur together, so no read/write collision is used.
    always_ff @(posedge aclk) begin
        if (write_enable)
            table_mem[address] <= write_entry;
        if (read_enable)
            read_entry <= table_mem[read_address];
    end

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            state <= CLEAR;
            address <= '0;
            used_voxels <= '0;
            lookup_valid <= 1'b0;
        end else begin
            if (lookup_ready)
                lookup_valid <= 1'b0;

            case (state)
                CLEAR: begin
                    address <= address + 1'b1;
                    if (address == ADDR_WIDTH'(TABLE_SIZE-1))
                        state <= IDLE;
                end

                IDLE: begin
                    if (accept) begin
                        address <= read_address;
                        state <= PROBE;
                    end
                end

                PROBE: begin
                    if (advance) begin
                        address <= address + 1'b1;
                    end else begin
                        lookup_valid <= 1'b1;
                        state <= IDLE;
                    end
                    if (allocate)
                        used_voxels <= used_voxels + 1'b1;
                end

                default: begin
                    state <= CLEAR;
                    address <= '0;
                    used_voxels <= '0;
                    lookup_valid <= 1'b0;
                end
            endcase
        end

        // Payload needs no reset. A response reserves its output register
        // when accepted, and remains stable until lookup_ready consumes it.
        if (accept) begin
            request_key <= {voxel_x, voxel_y, voxel_z};
            lookup_rssi_dbm <= voxel_rssi_dbm;
            attempts <= '0;
        end else if (advance) begin
            attempts <= attempts + 1'b1;
        end

        if (state == PROBE && !advance) begin
            lookup_slot <= match ? read_entry.slot :
                           allocate ? SLOT_WIDTH'(used_voxels) : '0;
            lookup_new <= allocate;
            lookup_rejected <= !match && !allocate;
        end
    end

    // synthesis translate_off
    initial begin
        if (TABLE_SIZE < 2 || (TABLE_SIZE & (TABLE_SIZE-1)) != 0)
            $fatal(1, "TABLE_SIZE must be a power of two, at least 2");
        if (MAX_VOXELS < 1 || MAX_VOXELS > TABLE_SIZE)
            $fatal(1, "MAX_VOXELS must be between 1 and TABLE_SIZE");
    end
    // synthesis translate_on

endmodule
