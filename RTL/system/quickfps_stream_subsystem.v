module quickfps_stream_subsystem #(
    parameter ADDR_W = 64,
    parameter AXI_DATA_W = 256,
    parameter COUNT_W = 24,
    parameter MCNT_W = 8,
    parameter CHUNK_POINTS = 256,
    parameter MAX_BURST_BEATS = 16
)(
    input  wire                         clk,
    input  wire                         rst_n,

    input  wire                         bucket_valid,
    output wire                         bucket_ready,
    input  wire [ADDR_W-1:0]            bucket_coord_addr,
    input  wire [ADDR_W-1:0]            bucket_dist_addr,
    input  wire [COUNT_W-1:0]           bucket_point_count,
    input  wire [MCNT_W-1:0]            bucket_merge_count,
    output wire                         bucket_done,
    output wire                         busy,

    // Coordinate stream written into the selected ping-pong point buffer.
    output wire                         coord_stream_valid,
    input  wire                         coord_stream_ready,
    output wire [AXI_DATA_W-1:0]        coord_stream_data,
    output wire                         coord_stream_last,

    // MDT read stream written into the selected ping-pong distance buffer.
    output wire                         dist_stream_valid,
    input  wire                         dist_stream_ready,
    output wire [AXI_DATA_W-1:0]        dist_stream_data,
    output wire                         dist_stream_last,

    // Updated MDT stream sourced by the selected ping-pong distance buffer.
    input  wire                         write_stream_valid,
    output wire                         write_stream_ready,
    input  wire [AXI_DATA_W-1:0]        write_stream_data,

    // The existing 4x4 Point-Engine is attached here.  A compute command is
    // issued only after both coordinate and MDT DMA reads for the slot finish.
    output wire                         compute_start,
    input  wire                         compute_ready,
    output wire [COUNT_W-1:0]           compute_point_count,
    output wire [MCNT_W-1:0]            compute_merge_count,
    output wire                         compute_slot,
    input  wire                         compute_done,

    // Coordinate-read AXI4 master.
    output wire                         c_axi_arvalid,
    input  wire                         c_axi_arready,
    output wire [ADDR_W-1:0]            c_axi_araddr,
    output wire [7:0]                   c_axi_arlen,
    output wire [2:0]                   c_axi_arsize,
    output wire [1:0]                   c_axi_arburst,
    input  wire                         c_axi_rvalid,
    output wire                         c_axi_rready,
    input  wire [AXI_DATA_W-1:0]        c_axi_rdata,
    input  wire                         c_axi_rlast,
    input  wire [1:0]                   c_axi_rresp,

    // MDT-read AXI4 master.
    output wire                         d_axi_arvalid,
    input  wire                         d_axi_arready,
    output wire [ADDR_W-1:0]            d_axi_araddr,
    output wire [7:0]                   d_axi_arlen,
    output wire [2:0]                   d_axi_arsize,
    output wire [1:0]                   d_axi_arburst,
    input  wire                         d_axi_rvalid,
    output wire                         d_axi_rready,
    input  wire [AXI_DATA_W-1:0]        d_axi_rdata,
    input  wire                         d_axi_rlast,
    input  wire [1:0]                   d_axi_rresp,

    // MDT-write AXI4 master.
    output wire                         w_axi_awvalid,
    input  wire                         w_axi_awready,
    output wire [ADDR_W-1:0]            w_axi_awaddr,
    output wire [7:0]                   w_axi_awlen,
    output wire [2:0]                   w_axi_awsize,
    output wire [1:0]                   w_axi_awburst,
    output wire                         w_axi_wvalid,
    input  wire                         w_axi_wready,
    output wire [AXI_DATA_W-1:0]        w_axi_wdata,
    output wire [AXI_DATA_W/8-1:0]      w_axi_wstrb,
    output wire                         w_axi_wlast,
    input  wire                         w_axi_bvalid,
    output wire                         w_axi_bready,
    input  wire [1:0]                   w_axi_bresp
);
    wire coord_cmd_valid, coord_cmd_ready, coord_dma_done, coord_dma_busy;
    wire [ADDR_W-1:0] coord_cmd_addr;
    wire [COUNT_W+4-1:0] coord_cmd_bytes;
    wire dist_rd_cmd_valid, dist_rd_cmd_ready, dist_rd_done, dist_rd_busy;
    wire [ADDR_W-1:0] dist_rd_cmd_addr;
    wire [COUNT_W+2-1:0] dist_rd_cmd_bytes;
    wire dist_wr_cmd_valid, dist_wr_cmd_ready, dist_wr_done, dist_wr_busy;
    wire [ADDR_W-1:0] dist_wr_cmd_addr;
    wire [COUNT_W+2-1:0] dist_wr_cmd_bytes;
    wire [31:0] coord_bytes_completed;
    wire [31:0] dist_rd_bytes_completed;
    wire [31:0] dist_wr_bytes_completed;

    pingpong_chunk_ctrl #(
        .ADDR_W(ADDR_W),
        .COUNT_W(COUNT_W),
        .MCNT_W(MCNT_W),
        .CHUNK_POINTS(CHUNK_POINTS),
        .COORD_BYTES(12),
        .DIST_BYTES(4)
    ) u_chunk_ctrl (
        .clk(clk), .rst_n(rst_n),
        .bucket_valid(bucket_valid), .bucket_ready(bucket_ready),
        .bucket_coord_addr(bucket_coord_addr),
        .bucket_dist_addr(bucket_dist_addr),
        .bucket_point_count(bucket_point_count),
        .bucket_merge_count(bucket_merge_count),
        .bucket_done(bucket_done), .busy(busy),
        .coord_cmd_valid(coord_cmd_valid), .coord_cmd_ready(coord_cmd_ready),
        .coord_cmd_addr(coord_cmd_addr), .coord_cmd_bytes(coord_cmd_bytes),
        .coord_done(coord_dma_done),
        .dist_rd_cmd_valid(dist_rd_cmd_valid),
        .dist_rd_cmd_ready(dist_rd_cmd_ready),
        .dist_rd_cmd_addr(dist_rd_cmd_addr),
        .dist_rd_cmd_bytes(dist_rd_cmd_bytes), .dist_rd_done(dist_rd_done),
        .dist_wr_cmd_valid(dist_wr_cmd_valid),
        .dist_wr_cmd_ready(dist_wr_cmd_ready),
        .dist_wr_cmd_addr(dist_wr_cmd_addr),
        .dist_wr_cmd_bytes(dist_wr_cmd_bytes), .dist_wr_done(dist_wr_done),
        .compute_start(compute_start), .compute_ready(compute_ready),
        .compute_point_count(compute_point_count),
        .compute_merge_count(compute_merge_count),
        .compute_slot(compute_slot), .compute_done(compute_done)
    );

    axi_burst_reader #(
        .ADDR_W(ADDR_W), .DATA_W(AXI_DATA_W),
        .MAX_BURST_BEATS(MAX_BURST_BEATS)
    ) u_coord_reader (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(coord_cmd_valid), .cmd_ready(coord_cmd_ready),
        .cmd_addr(coord_cmd_addr),
        .cmd_bytes({{(32-(COUNT_W+4)){1'b0}}, coord_cmd_bytes}),
        .done(coord_dma_done), .busy(coord_dma_busy),
        .m_axi_arvalid(c_axi_arvalid), .m_axi_arready(c_axi_arready),
        .m_axi_araddr(c_axi_araddr), .m_axi_arlen(c_axi_arlen),
        .m_axi_arsize(c_axi_arsize), .m_axi_arburst(c_axi_arburst),
        .m_axi_rvalid(c_axi_rvalid), .m_axi_rready(c_axi_rready),
        .m_axi_rdata(c_axi_rdata), .m_axi_rlast(c_axi_rlast),
        .m_axi_rresp(c_axi_rresp),
        .out_valid(coord_stream_valid), .out_ready(coord_stream_ready),
        .out_data(coord_stream_data), .out_last(coord_stream_last),
        .bytes_completed(coord_bytes_completed)
    );

    axi_burst_reader #(
        .ADDR_W(ADDR_W), .DATA_W(AXI_DATA_W),
        .MAX_BURST_BEATS(MAX_BURST_BEATS)
    ) u_dist_reader (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(dist_rd_cmd_valid), .cmd_ready(dist_rd_cmd_ready),
        .cmd_addr(dist_rd_cmd_addr),
        .cmd_bytes({{(32-(COUNT_W+2)){1'b0}}, dist_rd_cmd_bytes}),
        .done(dist_rd_done), .busy(dist_rd_busy),
        .m_axi_arvalid(d_axi_arvalid), .m_axi_arready(d_axi_arready),
        .m_axi_araddr(d_axi_araddr), .m_axi_arlen(d_axi_arlen),
        .m_axi_arsize(d_axi_arsize), .m_axi_arburst(d_axi_arburst),
        .m_axi_rvalid(d_axi_rvalid), .m_axi_rready(d_axi_rready),
        .m_axi_rdata(d_axi_rdata), .m_axi_rlast(d_axi_rlast),
        .m_axi_rresp(d_axi_rresp),
        .out_valid(dist_stream_valid), .out_ready(dist_stream_ready),
        .out_data(dist_stream_data), .out_last(dist_stream_last),
        .bytes_completed(dist_rd_bytes_completed)
    );

    axi_burst_writer #(
        .ADDR_W(ADDR_W), .DATA_W(AXI_DATA_W),
        .MAX_BURST_BEATS(MAX_BURST_BEATS)
    ) u_dist_writer (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(dist_wr_cmd_valid), .cmd_ready(dist_wr_cmd_ready),
        .cmd_addr(dist_wr_cmd_addr),
        .cmd_bytes({{(32-(COUNT_W+2)){1'b0}}, dist_wr_cmd_bytes}),
        .done(dist_wr_done), .busy(dist_wr_busy),
        .in_valid(write_stream_valid), .in_ready(write_stream_ready),
        .in_data(write_stream_data),
        .m_axi_awvalid(w_axi_awvalid), .m_axi_awready(w_axi_awready),
        .m_axi_awaddr(w_axi_awaddr), .m_axi_awlen(w_axi_awlen),
        .m_axi_awsize(w_axi_awsize), .m_axi_awburst(w_axi_awburst),
        .m_axi_wvalid(w_axi_wvalid), .m_axi_wready(w_axi_wready),
        .m_axi_wdata(w_axi_wdata), .m_axi_wstrb(w_axi_wstrb),
        .m_axi_wlast(w_axi_wlast),
        .m_axi_bvalid(w_axi_bvalid), .m_axi_bready(w_axi_bready),
        .m_axi_bresp(w_axi_bresp),
        .bytes_completed(dist_wr_bytes_completed)
    );

    // synopsys translate_off
    initial begin
        if (COUNT_W + 4 > 32)
            $fatal(1, "quickfps_stream_subsystem: coordinate byte count exceeds DMA LEN_W");
        if (COUNT_W + 2 > 32)
            $fatal(1, "quickfps_stream_subsystem: distance byte count exceeds DMA LEN_W");
    end
    always @(posedge clk) begin
        if (coord_dma_done && coord_bytes_completed == 0)
            $fatal(1, "quickfps_stream_subsystem: zero-byte coordinate completion");
        if (dist_rd_done && dist_rd_bytes_completed == 0)
            $fatal(1, "quickfps_stream_subsystem: zero-byte MDT read completion");
        if (dist_wr_done && dist_wr_bytes_completed == 0)
            $fatal(1, "quickfps_stream_subsystem: zero-byte MDT write completion");
    end
    // synopsys translate_on
endmodule
