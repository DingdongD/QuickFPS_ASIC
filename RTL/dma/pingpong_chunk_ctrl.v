module pingpong_chunk_ctrl #(
    parameter ADDR_W = 64,
    parameter COUNT_W = 24,
    parameter MCNT_W = 8,
    parameter CHUNK_POINTS = 256,
    parameter COORD_BYTES = 12,
    parameter DIST_BYTES = 4
)(
    input  wire                   clk,
    input  wire                   rst_n,

    input  wire                   bucket_valid,
    output wire                   bucket_ready,
    input  wire [ADDR_W-1:0]      bucket_point_ptr,
    input  wire [COUNT_W-1:0]     bucket_point_count,
    input  wire [MCNT_W-1:0]      bucket_merge_count,
    output reg                    bucket_done,
    output reg                    busy,

    output reg                    coord_cmd_valid,
    input  wire                   coord_cmd_ready,
    output reg [ADDR_W-1:0]       coord_cmd_addr,
    output reg [COUNT_W+4-1:0]    coord_cmd_bytes,
    input  wire                   coord_done,

    output reg                    dist_rd_cmd_valid,
    input  wire                   dist_rd_cmd_ready,
    output reg [ADDR_W-1:0]       dist_rd_cmd_addr,
    output reg [COUNT_W+2-1:0]    dist_rd_cmd_bytes,
    input  wire                   dist_rd_done,

    output reg                    dist_wr_cmd_valid,
    input  wire                   dist_wr_cmd_ready,
    output reg [ADDR_W-1:0]       dist_wr_cmd_addr,
    output reg [COUNT_W+2-1:0]    dist_wr_cmd_bytes,
    input  wire                   dist_wr_done,

    output reg                    compute_start,
    input  wire                   compute_ready,
    output reg [COUNT_W-1:0]      compute_point_count,
    output reg [MCNT_W-1:0]       compute_merge_count,
    output reg                    compute_slot,
    input  wire                   compute_done
);
    localparam SLOT_EMPTY   = 3'd0;
    localparam SLOT_LOADING = 3'd1;
    localparam SLOT_LOADED  = 3'd2;
    localparam SLOT_COMPUTE = 3'd3;
    localparam SLOT_WRITEQ  = 3'd4;
    localparam SLOT_WRITING = 3'd5;

    reg [2:0] slot_state [0:1];
    reg [COUNT_W-1:0] slot_offset [0:1];
    reg [COUNT_W-1:0] slot_points [0:1];

    reg [ADDR_W-1:0]  point_ptr;
    reg [COUNT_W-1:0] point_count;
    reg [MCNT_W-1:0]  merge_count;
    reg [COUNT_W-1:0] total_chunks;
    reg [COUNT_W-1:0] next_load;
    reg [COUNT_W-1:0] complete_count;

    reg load_inflight;
    reg load_slot;
    reg coord_seen;
    reg dist_seen;
    reg compute_inflight;
    reg compute_active_slot;
    reg write_inflight;
    reg write_slot;

    wire [COUNT_W-1:0] load_offset = next_load * CHUNK_POINTS;
    wire [COUNT_W-1:0] load_remaining = point_count - load_offset;
    wire [COUNT_W-1:0] load_points =
        (load_remaining < CHUNK_POINTS) ? load_remaining : CHUNK_POINTS;
    wire candidate_slot = next_load[0];
    wire candidate_empty = slot_state[candidate_slot] == SLOT_EMPTY;
    wire reads_ready = coord_cmd_ready && dist_rd_cmd_ready;

    wire loaded_available = (slot_state[0] == SLOT_LOADED) ||
                            (slot_state[1] == SLOT_LOADED);
    wire loaded_slot = (slot_state[0] == SLOT_LOADED) ? 1'b0 : 1'b1;
    wire write_available = (slot_state[0] == SLOT_WRITEQ) ||
                           (slot_state[1] == SLOT_WRITEQ);
    wire queued_write_slot = (slot_state[0] == SLOT_WRITEQ) ? 1'b0 : 1'b1;

    assign bucket_ready = !busy;

    integer s;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy <= 1'b0;
            bucket_done <= 1'b0;
            coord_cmd_valid <= 1'b0;
            dist_rd_cmd_valid <= 1'b0;
            dist_wr_cmd_valid <= 1'b0;
            compute_start <= 1'b0;
            coord_cmd_addr <= {ADDR_W{1'b0}};
            dist_rd_cmd_addr <= {ADDR_W{1'b0}};
            dist_wr_cmd_addr <= {ADDR_W{1'b0}};
            coord_cmd_bytes <= {(COUNT_W+4){1'b0}};
            dist_rd_cmd_bytes <= {(COUNT_W+2){1'b0}};
            dist_wr_cmd_bytes <= {(COUNT_W+2){1'b0}};
            compute_point_count <= {COUNT_W{1'b0}};
            compute_merge_count <= {MCNT_W{1'b0}};
            compute_slot <= 1'b0;
            point_ptr <= {ADDR_W{1'b0}};
            point_count <= {COUNT_W{1'b0}};
            merge_count <= {MCNT_W{1'b0}};
            total_chunks <= {COUNT_W{1'b0}};
            next_load <= {COUNT_W{1'b0}};
            complete_count <= {COUNT_W{1'b0}};
            load_inflight <= 1'b0;
            load_slot <= 1'b0;
            coord_seen <= 1'b0;
            dist_seen <= 1'b0;
            compute_inflight <= 1'b0;
            compute_active_slot <= 1'b0;
            write_inflight <= 1'b0;
            write_slot <= 1'b0;
            for (s = 0; s < 2; s = s + 1) begin
                slot_state[s] <= SLOT_EMPTY;
                slot_offset[s] <= {COUNT_W{1'b0}};
                slot_points[s] <= {COUNT_W{1'b0}};
            end
        end else begin
            bucket_done <= 1'b0;
            coord_cmd_valid <= 1'b0;
            dist_rd_cmd_valid <= 1'b0;
            dist_wr_cmd_valid <= 1'b0;
            compute_start <= 1'b0;

            if (bucket_valid && bucket_ready) begin
                point_ptr <= bucket_point_ptr;
                point_count <= bucket_point_count;
                merge_count <= bucket_merge_count;
                total_chunks <= (bucket_point_count + CHUNK_POINTS - 1) /
                                CHUNK_POINTS;
                next_load <= {COUNT_W{1'b0}};
                complete_count <= {COUNT_W{1'b0}};
                load_inflight <= 1'b0;
                compute_inflight <= 1'b0;
                write_inflight <= 1'b0;
                coord_seen <= 1'b0;
                dist_seen <= 1'b0;
                slot_state[0] <= SLOT_EMPTY;
                slot_state[1] <= SLOT_EMPTY;
                if (bucket_point_count == {COUNT_W{1'b0}}) begin
                    bucket_done <= 1'b1;
                    busy <= 1'b0;
                end else begin
                    busy <= 1'b1;
                end
            end

            if (busy) begin
                if (!load_inflight && next_load < total_chunks &&
                    candidate_empty && reads_ready) begin
                    coord_cmd_valid <= 1'b1;
                    dist_rd_cmd_valid <= 1'b1;
                    coord_cmd_addr <= point_ptr + load_offset * COORD_BYTES;
                    dist_rd_cmd_addr <= point_ptr + load_offset * DIST_BYTES;
                    coord_cmd_bytes <= load_points * COORD_BYTES;
                    dist_rd_cmd_bytes <= load_points * DIST_BYTES;
                    slot_state[candidate_slot] <= SLOT_LOADING;
                    slot_offset[candidate_slot] <= load_offset;
                    slot_points[candidate_slot] <= load_points;
                    load_slot <= candidate_slot;
                    load_inflight <= 1'b1;
                    coord_seen <= 1'b0;
                    dist_seen <= 1'b0;
                end

                if (load_inflight) begin
                    if (coord_done)
                        coord_seen <= 1'b1;
                    if (dist_rd_done)
                        dist_seen <= 1'b1;
                    if ((coord_seen || coord_done) &&
                        (dist_seen || dist_rd_done)) begin
                        slot_state[load_slot] <= SLOT_LOADED;
                        load_inflight <= 1'b0;
                        next_load <= next_load + 1'b1;
                    end
                end

                if (!compute_inflight && loaded_available && compute_ready) begin
                    compute_start <= 1'b1;
                    compute_point_count <= slot_points[loaded_slot];
                    compute_merge_count <= merge_count;
                    compute_slot <= loaded_slot;
                    slot_state[loaded_slot] <= SLOT_COMPUTE;
                    compute_active_slot <= loaded_slot;
                    compute_inflight <= 1'b1;
                end

                if (compute_inflight && compute_done) begin
                    slot_state[compute_active_slot] <= SLOT_WRITEQ;
                    compute_inflight <= 1'b0;
                end

                if (!write_inflight && write_available && dist_wr_cmd_ready) begin
                    dist_wr_cmd_valid <= 1'b1;
                    dist_wr_cmd_addr <= point_ptr +
                                        slot_offset[queued_write_slot] * DIST_BYTES;
                    dist_wr_cmd_bytes <= slot_points[queued_write_slot] * DIST_BYTES;
                    slot_state[queued_write_slot] <= SLOT_WRITING;
                    write_slot <= queued_write_slot;
                    write_inflight <= 1'b1;
                end

                if (write_inflight && dist_wr_done) begin
                    slot_state[write_slot] <= SLOT_EMPTY;
                    write_inflight <= 1'b0;
                    complete_count <= complete_count + 1'b1;
                    if (complete_count + 1'b1 >= total_chunks) begin
                        busy <= 1'b0;
                        bucket_done <= 1'b1;
                    end
                end
            end
        end
    end

    // synopsys translate_off
    initial begin
        if (CHUNK_POINTS < 1)
            $fatal(1, "pingpong_chunk_ctrl: CHUNK_POINTS must be positive");
        if (COORD_BYTES < 1 || DIST_BYTES < 1)
            $fatal(1, "pingpong_chunk_ctrl: point byte widths must be positive");
    end
    // synopsys translate_on
endmodule
