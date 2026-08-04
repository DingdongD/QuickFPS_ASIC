module bucket_engine #(
    parameter BIDX_W  = 9,
    parameter PIDX_W  = 18,
    parameter NUMP_W  = 16,
    parameter ADDR_W  = 32,
    parameter MCNT_W  = 8,
    parameter MB_CAP  = 32,
    parameter FIFO_DEPTH = 8,
    parameter ENTRY_W = 368 + PIDX_W + MCNT_W,
    parameter BF_W    = BIDX_W + ADDR_W + NUMP_W + 96 + MCNT_W,
    parameter FP_W    = BIDX_W + 96 + 32 + PIDX_W
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               start,
    output reg                busy,
    output reg                done,
    input  wire [PIDX_W-1:0]  sample_n,
    input  wire [BIDX_W-1:0]  bucket_m,
    input  wire [31:0]        p0x, p0y, p0z,
    input  wire [PIDX_W-1:0]  p0idx,
    output wire [BIDX_W-1:0]  bb_raddr,
    input  wire [ENTRY_W-1:0] bb_rdata,
    output reg                bb_wen,
    output reg  [BIDX_W-1:0]  bb_waddr,
    output reg  [ENTRY_W-1:0] bb_wdata,
    output reg                mb_wen,
    output reg                mb_clr,
    output reg  [BIDX_W-1:0]  mb_addr,
    output reg  [95:0]        mb_wdata,
    output wire               bkt_empty,
    output wire [BF_W-1:0]    bkt_rdata,
    input  wire               bkt_ren,
    output wire               fp_full,
    input  wire               fp_wen,
    input  wire [FP_W-1:0]    fp_wdata,
    output reg                res_wen,
    output reg  [PIDX_W-1:0]  res_addr,
    output reg  [95+PIDX_W:0] res_wdata
);
    localparam E_MINX=0,  E_MINY=32, E_MINZ=64, E_MAXX=96, E_MAXY=128, E_MAXZ=160;
    localparam E_PTR=192, E_NUMP=224, E_FX=240, E_FY=272, E_FZ=304, E_FDIST=336;
    localparam E_FIDX=368, E_MCNT=E_FIDX+PIDX_W;
    localparam META_W = ENTRY_W + BIDX_W;

    localparam S_IDLE=0, S_INITP0=1, S_ITERINIT=2, S_TRAVEL=3;
    localparam S_TDONE=4, S_COLLECT=5, S_ITEREND=6, S_DONE=7;
    reg [2:0] state;

    reg [PIDX_W-1:0] cnt;
    reg [BIDX_W-1:0] winner_bidx;
    reg              first_iter;
    reg [31:0]       sx, sy, sz;
    reg [BIDX_W:0]   fb_bi;
    reg [BIDX_W:0]   hb_cnt;
    reg [BIDX_W:0]   issued_cnt, collect_cnt;

    wire [BIDX_W:0]  M_wide = {1'b0, bucket_m} + 1'b1;
    wire [BIDX_W-1:0] fb_jm1 = fb_bi[BIDX_W-1:0] - 1'b1;
    wire [BIDX_W-1:0] fb_bucket_id = (fb_bi=={(BIDX_W+1){1'b0}}) ? winner_bidx
                                   : (fb_jm1 < winner_bidx) ? fb_jm1 : (fb_jm1 + 1'b1);
    wire feeding = (state==S_TRAVEL) && (fb_bi <= {1'b0,bucket_m});

    wire              fp_rd_empty;
    wire [FP_W-1:0]   fp_rd_data;
    wire              fp_rd_ren;
    wire [31:0]       nf_x    = fp_rd_data[0   +: 32];
    wire [31:0]       nf_y    = fp_rd_data[32  +: 32];
    wire [31:0]       nf_z    = fp_rd_data[64  +: 32];
    wire [31:0]       nf_dist = fp_rd_data[96  +: 32];
    wire [PIDX_W-1:0] nf_idx  = fp_rd_data[128 +: PIDX_W];
    wire [BIDX_W-1:0] nf_bid  = fp_rd_data[128+PIDX_W +: BIDX_W];

    assign bb_raddr = (state==S_COLLECT) ? nf_bid :
                      (feeding ? fb_bucket_id : winner_bidx);

    wire              cd_out_valid;
    wire [META_W-1:0] cd_out_meta;
    wire [31:0]       cd_dlb, cd_d;
    bucket_cd #(.META_W(META_W)) u_cd (
        .clk(clk), .rst_n(rst_n),
        .in_valid(feeding),
        .meta_in({fb_bucket_id, bb_rdata}),
        .qx(sx), .qy(sy), .qz(sz),
        .minx(bb_rdata[E_MINX +:32]), .miny(bb_rdata[E_MINY +:32]), .minz(bb_rdata[E_MINZ +:32]),
        .maxx(bb_rdata[E_MAXX +:32]), .maxy(bb_rdata[E_MAXY +:32]), .maxz(bb_rdata[E_MAXZ +:32]),
        .fpx(bb_rdata[E_FX +:32]), .fpy(bb_rdata[E_FY +:32]), .fpz(bb_rdata[E_FZ +:32]),
        .out_valid(cd_out_valid), .out_meta(cd_out_meta),
        .out_dlb(cd_dlb), .out_d(cd_d)
    );

    wire [ENTRY_W-1:0] m_entry = cd_out_meta[0 +: ENTRY_W];
    wire [BIDX_W-1:0]  m_bid   = cd_out_meta[ENTRY_W +: BIDX_W];
    wire [31:0]        m_fx    = m_entry[E_FX +:32];
    wire [31:0]        m_fy    = m_entry[E_FY +:32];
    wire [31:0]        m_fz    = m_entry[E_FZ +:32];
    wire [31:0]        m_fdist = m_entry[E_FDIST +:32];
    wire [PIDX_W-1:0]  m_fidx  = m_entry[E_FIDX +:PIDX_W];
    wire [MCNT_W-1:0]  m_mcnt  = m_entry[E_MCNT +:MCNT_W];
    wire [NUMP_W-1:0]  m_nump  = m_entry[E_NUMP +:NUMP_W];
    wire [ADDR_W-1:0]  m_ptr   = m_entry[E_PTR +:ADDR_W];

    wire raw_issue, raw_defer, raw_skip;
    bucket_ib u_ib (
        .valid(cd_out_valid), .first_iter(first_iter),
        .fdist(m_fdist), .dlb(cd_dlb), .d(cd_d),
        .do_issue(raw_issue), .do_defer(raw_defer), .do_skip(raw_skip)
    );

    wire mb_full  = (m_mcnt >= MB_CAP[MCNT_W-1:0]);
    wire ib_issue = raw_issue | (raw_defer & mb_full);
    wire ib_defer = raw_defer & ~mb_full;

    reg              best_valid;
    reg [31:0]       best_x,best_y,best_z,best_dist;
    reg [PIDX_W-1:0] best_idx;
    reg [BIDX_W-1:0] best_bidx;
    wire take_travel  = ~best_valid | (m_fdist[30:0] > best_dist[30:0]);
    wire take_collect = ~best_valid | (nf_dist[30:0] > best_dist[30:0]);

    wire [ENTRY_W-1:0] dwb_entry = { (m_mcnt + 1'b1), m_entry[E_MCNT-1:0] };

    wire [ENTRY_W-1:0] cwb_entry;
    assign cwb_entry[E_MINX +:32]=bb_rdata[E_MINX +:32];
    assign cwb_entry[E_MINY +:32]=bb_rdata[E_MINY +:32];
    assign cwb_entry[E_MINZ +:32]=bb_rdata[E_MINZ +:32];
    assign cwb_entry[E_MAXX +:32]=bb_rdata[E_MAXX +:32];
    assign cwb_entry[E_MAXY +:32]=bb_rdata[E_MAXY +:32];
    assign cwb_entry[E_MAXZ +:32]=bb_rdata[E_MAXZ +:32];
    assign cwb_entry[E_PTR +:ADDR_W]=bb_rdata[E_PTR +:ADDR_W];
    assign cwb_entry[E_NUMP +:NUMP_W]=bb_rdata[E_NUMP +:NUMP_W];
    assign cwb_entry[E_FX +:32]=nf_x;
    assign cwb_entry[E_FY +:32]=nf_y;
    assign cwb_entry[E_FZ +:32]=nf_z;
    assign cwb_entry[E_FDIST +:32]=nf_dist;
    assign cwb_entry[E_FIDX +:PIDX_W]=nf_idx;
    assign cwb_entry[E_MCNT +:MCNT_W]={MCNT_W{1'b0}};

    wire            bkt_wr      = (state==S_TRAVEL) && cd_out_valid && ib_issue;
    wire [BF_W-1:0] bkt_wr_data = {m_mcnt, sz,sy,sx, m_nump, m_ptr, m_bid};
    wire            bkt_wr_full;
    sync_fifo #(.W(BF_W), .DEPTH(FIFO_DEPTH)) u_bkt_fifo (
        .clk(clk), .rst_n(rst_n),
        .wen(bkt_wr), .wdata(bkt_wr_data), .full(bkt_wr_full),
        .ren(bkt_ren), .rdata(bkt_rdata), .empty(bkt_empty)
    );

    sync_fifo #(.W(FP_W), .DEPTH(FIFO_DEPTH)) u_fp_fifo (
        .clk(clk), .rst_n(rst_n),
        .wen(fp_wen), .wdata(fp_wdata), .full(fp_full),
        .ren(fp_rd_ren), .rdata(fp_rd_data), .empty(fp_rd_empty)
    );
    assign fp_rd_ren = (state==S_COLLECT) && !fp_rd_empty;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state<=S_IDLE; busy<=0; done<=0;
            bb_wen<=0; mb_wen<=0; mb_clr<=0; res_wen<=0;
            cnt<=0; winner_bidx<=0; first_iter<=0;
            sx<=0; sy<=0; sz<=0; fb_bi<=0; hb_cnt<=0;
            issued_cnt<=0; collect_cnt<=0;
            bb_waddr<=0; bb_wdata<=0; mb_addr<=0; mb_wdata<=0;
            res_addr<=0; res_wdata<=0;
        end else begin
            bb_wen<=0; mb_wen<=0; mb_clr<=0; res_wen<=0;
            case (state)
            S_IDLE: begin
                done<=0;
                if (start) begin
                    busy<=1; cnt<=1; first_iter<=1; winner_bidx<=0;
                    sx<=p0x; sy<=p0y; sz<=p0z;
                    res_wen<=1; res_addr<={PIDX_W{1'b0}}; res_wdata<={p0idx,p0z,p0y,p0x};
                    state<=S_INITP0;
                end
            end
            S_INITP0: state <= (cnt >= sample_n) ? S_DONE : S_ITERINIT;
            S_ITERINIT: begin
                fb_bi<=0; hb_cnt<=0; best_valid<=0; best_dist<=0;
                issued_cnt<=0; collect_cnt<=0;
                first_iter<=(cnt=={{(PIDX_W-1){1'b0}},1'b1});
                state<=S_TRAVEL;
            end
            S_TRAVEL: begin
                if (feeding) fb_bi <= fb_bi + 1'b1;
                if (cd_out_valid) begin
                    if (ib_issue) begin
                        issued_cnt <= issued_cnt + 1'b1;
                    end else if (ib_defer) begin
                        mb_wen<=1; mb_addr<=m_bid; mb_wdata<={sz,sy,sx};
                        bb_wen<=1; bb_waddr<=m_bid; bb_wdata<=dwb_entry;
                        if (take_travel) begin
                            best_valid<=1; best_dist<=m_fdist; best_x<=m_fx; best_y<=m_fy; best_z<=m_fz;
                            best_idx<=m_fidx; best_bidx<=m_bid;
                        end
                    end else begin
                        if (take_travel) begin
                            best_valid<=1; best_dist<=m_fdist; best_x<=m_fx; best_y<=m_fy; best_z<=m_fz;
                            best_idx<=m_fidx; best_bidx<=m_bid;
                        end
                    end
                    hb_cnt <= hb_cnt + 1'b1;
                    if (hb_cnt + 1'b1 >= M_wide) state<=S_TDONE;
                end
            end
            S_TDONE: state <= (issued_cnt=={(BIDX_W+1){1'b0}}) ? S_ITEREND : S_COLLECT;
            S_COLLECT: if (!fp_rd_empty) begin
                bb_wen<=1; bb_waddr<=nf_bid; bb_wdata<=cwb_entry;
                mb_clr<=1; mb_addr<=nf_bid;
                if (take_collect) begin
                    best_valid<=1; best_dist<=nf_dist; best_x<=nf_x; best_y<=nf_y; best_z<=nf_z;
                    best_idx<=nf_idx; best_bidx<=nf_bid;
                end
                collect_cnt<=collect_cnt+1'b1;
                if (collect_cnt + 1'b1 >= issued_cnt) state<=S_ITEREND;
            end
            S_ITEREND: begin
                res_wen<=1; res_addr<=cnt; res_wdata<={best_idx,best_z,best_y,best_x};
                sx<=best_x; sy<=best_y; sz<=best_z;
                winner_bidx<=best_bidx;
                if (cnt + 1'b1 >= sample_n) state<=S_DONE;
                else begin cnt<=cnt+1'b1; state<=S_ITERINIT; end
            end
            S_DONE: begin
                busy<=0; done<=1;
                if (!start) state<=S_IDLE;
            end
            default: state<=S_IDLE;
            endcase
        end
    end

    // synopsys translate_off
    always @(posedge clk)
        if (busy && (M_wide > FIFO_DEPTH))
            $fatal(1, "bucket_engine: M=%0d > FIFO_DEPTH=%0d", M_wide, FIFO_DEPTH);
    // synopsys translate_on
endmodule
