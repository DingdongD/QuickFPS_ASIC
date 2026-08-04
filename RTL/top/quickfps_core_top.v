module quickfps_core_top #(
    parameter BIDX_W  = 9,
    parameter PIDX_W  = 18,
    parameter NUMP_W  = 16,
    parameter ADDR_W  = 32,
    parameter MCNT_W  = 8,
    parameter MB_CAP  = 32,
    parameter FIFO_DEPTH = 8,
    parameter L = 4,
    parameter R = 4,
    parameter LIDX_W = 11,
    parameter BUCKETS = 512,
    parameter POINT_DEPTH = (1 << PIDX_W),
    parameter ENTRY_W = 368 + PIDX_W + MCNT_W,
    parameter BF_W = BIDX_W + ADDR_W + NUMP_W + 96 + MCNT_W,
    parameter FP_W = BIDX_W + 96 + 32 + PIDX_W,
    parameter RESULT_W = 96 + PIDX_W
)(
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 start,
    output wire                 busy,
    output wire                 done,
    input  wire [PIDX_W-1:0]    sample_n,
    input  wire [BIDX_W-1:0]    bucket_m,
    input  wire [31:0]          p0x,
    input  wire [31:0]          p0y,
    input  wire [31:0]          p0z,
    input  wire [PIDX_W-1:0]    p0idx,

    // Host-side preload ports.  The host builds the two-level tree, reorders
    // points by bucket, writes coordinates and +INF MDT values, then asserts
    // start.  Host writes must be inactive while busy is high.
    input  wire                 host_bb_wen,
    input  wire [BIDX_W-1:0]    host_bb_waddr,
    input  wire [ENTRY_W-1:0]   host_bb_wdata,
    input  wire                 host_coord_wen,
    input  wire [PIDX_W-1:0]    host_coord_waddr,
    input  wire [95:0]          host_coord_wdata,
    input  wire                 host_dist_wen,
    input  wire [PIDX_W-1:0]    host_dist_waddr,
    input  wire [31:0]          host_dist_wdata,

    input  wire [PIDX_W-1:0]    result_raddr,
    output wire [RESULT_W-1:0]  result_rdata
);
    wire [BIDX_W-1:0] core_bb_raddr;
    wire [ENTRY_W-1:0] core_bb_rdata;
    wire core_bb_wen;
    wire [BIDX_W-1:0] core_bb_waddr;
    wire [ENTRY_W-1:0] core_bb_wdata;

    wire bb_mem_wen = core_bb_wen | host_bb_wen;
    wire [BIDX_W-1:0] bb_mem_waddr =
        core_bb_wen ? core_bb_waddr : host_bb_waddr;
    wire [ENTRY_W-1:0] bb_mem_wdata =
        core_bb_wen ? core_bb_wdata : host_bb_wdata;

    bucket_buffer #(
        .DEPTH(BUCKETS), .AW(BIDX_W), .WIDTH(ENTRY_W)
    ) u_bucket_buffer (
        .clk(clk),
        .raddr(core_bb_raddr), .rdata(core_bb_rdata),
        .wen(bb_mem_wen), .waddr(bb_mem_waddr), .wdata(bb_mem_wdata)
    );

    wire mb_wen, mb_clr;
    wire [BIDX_W-1:0] mb_addr;
    wire [95:0] mb_wdata;
    wire [BIDX_W-1:0] pe_mb_bid;
    wire [7:0] pe_mb_k;
    wire [95:0] pe_mb_rdata;
    wire [MCNT_W-1:0] pe_mb_count;

    merge_buffer #(
        .BUCKETS(BUCKETS), .BIDX_W(BIDX_W),
        .CAP(MB_CAP), .MCNT_W(MCNT_W)
    ) u_merge_buffer (
        .clk(clk), .rst_n(rst_n),
        .wen(mb_wen), .clr(mb_clr), .addr(mb_addr), .wdata(mb_wdata),
        .rd_bid(pe_mb_bid), .rd_slot(pe_mb_k),
        .rdata(pe_mb_rdata), .rd_count(pe_mb_count)
    );

    wire bkt_empty;
    wire [BF_W-1:0] bkt_rdata;
    wire bkt_ren;
    wire fp_full;
    wire fp_wen;
    wire [FP_W-1:0] fp_wdata;
    wire res_wen;
    wire [PIDX_W-1:0] res_waddr;
    wire [RESULT_W-1:0] res_wdata;

    bucket_engine #(
        .BIDX_W(BIDX_W), .PIDX_W(PIDX_W), .NUMP_W(NUMP_W),
        .ADDR_W(ADDR_W), .MCNT_W(MCNT_W), .MB_CAP(MB_CAP),
        .FIFO_DEPTH(FIFO_DEPTH), .ENTRY_W(ENTRY_W),
        .BF_W(BF_W), .FP_W(FP_W)
    ) u_bucket_engine (
        .clk(clk), .rst_n(rst_n), .start(start),
        .busy(busy), .done(done),
        .sample_n(sample_n), .bucket_m(bucket_m),
        .p0x(p0x), .p0y(p0y), .p0z(p0z), .p0idx(p0idx),
        .bb_raddr(core_bb_raddr), .bb_rdata(core_bb_rdata),
        .bb_wen(core_bb_wen), .bb_waddr(core_bb_waddr),
        .bb_wdata(core_bb_wdata),
        .mb_wen(mb_wen), .mb_clr(mb_clr),
        .mb_addr(mb_addr), .mb_wdata(mb_wdata),
        .bkt_empty(bkt_empty), .bkt_rdata(bkt_rdata), .bkt_ren(bkt_ren),
        .fp_full(fp_full), .fp_wen(fp_wen), .fp_wdata(fp_wdata),
        .res_wen(res_wen), .res_addr(res_waddr), .res_wdata(res_wdata)
    );

    wire [PIDX_W-1:0] coord_rbase;
    wire [R*96-1:0] coord_rdata;
    coord_buffer #(
        .DEPTH(POINT_DEPTH), .PIDX_W(PIDX_W), .R(R)
    ) u_coord_buffer (
        .clk(clk),
        .host_wen(host_coord_wen),
        .host_waddr(host_coord_waddr), .host_wdata(host_coord_wdata),
        .rd_base(coord_rbase), .rd_data(coord_rdata)
    );

    wire [PIDX_W-1:0] dist_rbase;
    wire [R*32-1:0] dist_rdata;
    wire [R-1:0] dist_wstrb;
    wire [PIDX_W-1:0] dist_wbase;
    wire [R*32-1:0] dist_wdata;
    dist_buffer #(
        .DEPTH(POINT_DEPTH), .PIDX_W(PIDX_W), .R(R)
    ) u_dist_buffer (
        .clk(clk),
        .host_wen(host_dist_wen),
        .host_waddr(host_dist_waddr), .host_wdata(host_dist_wdata),
        .rd_base(dist_rbase), .rd_data(dist_rdata),
        .core_wstrb(dist_wstrb), .core_wbase(dist_wbase),
        .core_wdata(dist_wdata)
    );

    point_engine_top #(
        .L(L), .R(R), .LIDX_W(LIDX_W),
        .BIDX_W(BIDX_W), .PIDX_W(PIDX_W),
        .NUMP_W(NUMP_W), .ADDR_W(ADDR_W), .MCNT_W(MCNT_W),
        .BF_W(BF_W), .FP_W(FP_W)
    ) u_point_engine_top (
        .clk(clk), .rst_n(rst_n),
        .bkt_empty(bkt_empty), .bkt_rdata(bkt_rdata), .bkt_ren(bkt_ren),
        .fp_full(fp_full), .fp_wen(fp_wen), .fp_wdata(fp_wdata),
        .mb_bid(pe_mb_bid), .mb_k(pe_mb_k), .mb_rdata(pe_mb_rdata),
        .co_addr(coord_rbase), .co_rdata(coord_rdata),
        .di_raddr(dist_rbase), .di_rdata(dist_rdata),
        .di_wstrb(dist_wstrb), .di_waddr(dist_wbase),
        .di_wdata(dist_wdata)
    );

    result_buffer #(
        .DEPTH(POINT_DEPTH), .PIDX_W(PIDX_W), .WIDTH(RESULT_W)
    ) u_result_buffer (
        .clk(clk),
        .wen(res_wen), .waddr(res_waddr), .wdata(res_wdata),
        .raddr(result_raddr), .rdata(result_rdata)
    );

    // synopsys translate_off
    always @(posedge clk) begin
        if (busy && (host_bb_wen || host_coord_wen || host_dist_wen))
            $fatal(1, "quickfps_core_top: host memory writes are not allowed while busy");
        if (core_bb_wen && host_bb_wen)
            $fatal(1, "quickfps_core_top: bucket-buffer write collision");
    end
    // synopsys translate_on
endmodule
