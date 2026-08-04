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
    // Last valid bucket index.  The actual bucket count is bucket_m + 1.
    input  wire [BIDX_W-1:0]  bucket_m,
    input  wire [31:0]        p0x, p0y, p0z,
    input  wire [PIDX_W-1:0]  p0idx,

    // Functional bucket-buffer interface.  bb_rdata is a combinational read
    // of bb_raddr; writes are synchronous.  A one-cycle SRAM adapter can be
    // added above this core without changing the algorithmic state machine.
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
    localparam E_MINX=0,   E_MINY=32,  E_MINZ=64;
    localparam E_MAXX=96,  E_MAXY=128, E_MAXZ=160;
    localparam E_PTR=192,  E_NUMP=224;
    localparam E_FX=240,   E_FY=272,   E_FZ=304;
    localparam E_FDIST=336, E_FIDX=368, E_MCNT=E_FIDX+PIDX_W;
    localparam META_W = ENTRY_W + BIDX_W;

    localparam S_IDLE       = 4'd0;
    localparam S_INITP0     = 4'd1;
    localparam S_ITERINIT   = 4'd2;
    localparam S_FETCH      = 4'd3;
    localparam S_WAIT_CD    = 4'd4;
    localparam S_ACTION     = 4'd5;
    localparam S_NEXT       = 4'd6;
    localparam S_TDONE      = 4'd7;
    localparam S_COLLECT    = 4'd8;
    localparam S_ITEREND    = 4'd9;
    localparam S_DONE       = 4'd10;
    reg [3:0] state;

    reg [PIDX_W-1:0] cnt;
    reg [BIDX_W-1:0] winner_bidx;
    reg              first_iter;
    reg [31:0]       sx, sy, sz;
    reg [BIDX_W:0]   travel_pos;
    reg [BIDX_W:0]   issued_cnt, collect_cnt;

    wire [BIDX_W:0] bucket_count = {1'b0, bucket_m} + 1'b1;
    wire [BIDX_W-1:0] pos_minus_one =
        travel_pos[BIDX_W-1:0] - 1'b1;
    wire [BIDX_W-1:0] travel_bid =
        (travel_pos == {(BIDX_W+1){1'b0}}) ? winner_bidx :
        (pos_minus_one < winner_bidx) ? pos_minus_one :
                                         (pos_minus_one + 1'b1);
    // Launch only one bucket at a time into the four-stage distance pipeline.
    // This functional controller sacrifices bucket-II=1 but gives lossless
    // backpressure with a small FIFO and is the reference control path for the
    // complete end-to-end core.
    wire cd_in_valid = (state == S_FETCH);
    wire cd_out_valid;
    wire [META_W-1:0] cd_out_meta;
    wire [31:0] cd_dlb, cd_d;
    bucket_cd #(.META_W(META_W)) u_cd (
        .clk(clk), .rst_n(rst_n),
        .in_valid(cd_in_valid),
        .meta_in({travel_bid, bb_rdata}),
        .qx(sx), .qy(sy), .qz(sz),
        .minx(bb_rdata[E_MINX +:32]),
        .miny(bb_rdata[E_MINY +:32]),
        .minz(bb_rdata[E_MINZ +:32]),
        .maxx(bb_rdata[E_MAXX +:32]),
        .maxy(bb_rdata[E_MAXY +:32]),
        .maxz(bb_rdata[E_MAXZ +:32]),
        .fpx(bb_rdata[E_FX +:32]),
        .fpy(bb_rdata[E_FY +:32]),
        .fpz(bb_rdata[E_FZ +:32]),
        .out_valid(cd_out_valid),
        .out_meta(cd_out_meta),
        .out_dlb(cd_dlb),
        .out_d(cd_d)
    );

    reg [ENTRY_W-1:0] pend_entry;
    reg [BIDX_W-1:0]  pend_bid;
    reg [31:0]         pend_dlb, pend_d;

    wire [31:0] pend_fx    = pend_entry[E_FX +:32];
    wire [31:0] pend_fy    = pend_entry[E_FY +:32];
    wire [31:0] pend_fz    = pend_entry[E_FZ +:32];
    wire [31:0] pend_fdist = pend_entry[E_FDIST +:32];
    wire [PIDX_W-1:0] pend_fidx = pend_entry[E_FIDX +:PIDX_W];
    wire [MCNT_W-1:0] pend_mcnt = pend_entry[E_MCNT +:MCNT_W];
    wire [NUMP_W-1:0] pend_nump = pend_entry[E_NUMP +:NUMP_W];
    wire [ADDR_W-1:0] pend_ptr  = pend_entry[E_PTR +:ADDR_W];

    wire raw_issue, raw_defer, raw_skip;
    bucket_ib u_ib (
        .valid(1'b1),
        .first_iter(first_iter),
        .fdist(pend_fdist),
        .dlb(pend_dlb),
        .d(pend_d),
        .do_issue(raw_issue),
        .do_defer(raw_defer),
        .do_skip(raw_skip)
    );
    wire merge_full = (pend_mcnt >= MB_CAP[MCNT_W-1:0]);
    wire act_issue = raw_issue | (raw_defer & merge_full);
    wire act_defer = raw_defer & ~merge_full;

    function automatic better;
        input [31:0] cand_dist;
        input [PIDX_W-1:0] cand_idx;
        input [31:0] cur_dist;
        input [PIDX_W-1:0] cur_idx;
        begin
            better = (cand_dist[30:0] > cur_dist[30:0]) ||
                     ((cand_dist[30:0] == cur_dist[30:0]) &&
                      (cand_idx < cur_idx));
        end
    endfunction

    reg              best_valid;
    reg [31:0]       best_x, best_y, best_z, best_dist;
    reg [PIDX_W-1:0] best_idx;
    reg [BIDX_W-1:0] best_bidx;

    wire take_pending = !best_valid ||
                        better(pend_fdist, pend_fidx,
                               best_dist, best_idx);

    wire [ENTRY_W-1:0] defer_entry =
        {(pend_mcnt + 1'b1), pend_entry[E_MCNT-1:0]};

    wire bkt_fifo_full;
    wire bkt_push = (state == S_ACTION) && act_issue && !bkt_fifo_full;
    wire [BF_W-1:0] bkt_push_data =
        {pend_mcnt, sz, sy, sx, pend_nump, pend_ptr, pend_bid};
    sync_fifo #(.W(BF_W), .DEPTH(FIFO_DEPTH)) u_bkt_fifo (
        .clk(clk), .rst_n(rst_n),
        .wen(bkt_push), .wdata(bkt_push_data), .full(bkt_fifo_full),
        .ren(bkt_ren), .rdata(bkt_rdata), .empty(bkt_empty)
    );

    wire fp_rd_empty;
    wire [FP_W-1:0] fp_rd_data;
    wire fp_rd_ren = (state == S_COLLECT) && !fp_rd_empty;
    sync_fifo #(.W(FP_W), .DEPTH(FIFO_DEPTH)) u_fp_fifo (
        .clk(clk), .rst_n(rst_n),
        .wen(fp_wen), .wdata(fp_wdata), .full(fp_full),
        .ren(fp_rd_ren), .rdata(fp_rd_data), .empty(fp_rd_empty)
    );

    wire [31:0] nf_x    = fp_rd_data[0 +:32];
    wire [31:0] nf_y    = fp_rd_data[32 +:32];
    wire [31:0] nf_z    = fp_rd_data[64 +:32];
    wire [31:0] nf_dist = fp_rd_data[96 +:32];
    wire [PIDX_W-1:0] nf_idx = fp_rd_data[128 +:PIDX_W];
    wire [BIDX_W-1:0] nf_bid =
        fp_rd_data[128+PIDX_W +:BIDX_W];
    assign bb_raddr = (state == S_COLLECT) ? nf_bid : travel_bid;
    wire take_return = !best_valid ||
                       better(nf_dist, nf_idx, best_dist, best_idx);

    reg [ENTRY_W-1:0] collect_entry;
    always @* begin
        collect_entry = bb_rdata;
        collect_entry[E_FX +:32] = nf_x;
        collect_entry[E_FY +:32] = nf_y;
        collect_entry[E_FZ +:32] = nf_z;
        collect_entry[E_FDIST +:32] = nf_dist;
        collect_entry[E_FIDX +:PIDX_W] = nf_idx;
        collect_entry[E_MCNT +:MCNT_W] = {MCNT_W{1'b0}};
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            busy <= 1'b0;
            done <= 1'b0;
            cnt <= {PIDX_W{1'b0}};
            winner_bidx <= {BIDX_W{1'b0}};
            first_iter <= 1'b0;
            sx <= 32'h0; sy <= 32'h0; sz <= 32'h0;
            travel_pos <= {(BIDX_W+1){1'b0}};
            issued_cnt <= {(BIDX_W+1){1'b0}};
            collect_cnt <= {(BIDX_W+1){1'b0}};
            pend_entry <= {ENTRY_W{1'b0}};
            pend_bid <= {BIDX_W{1'b0}};
            pend_dlb <= 32'h0;
            pend_d <= 32'h0;
            best_valid <= 1'b0;
            best_x <= 32'h0; best_y <= 32'h0; best_z <= 32'h0;
            best_dist <= 32'h0;
            best_idx <= {PIDX_W{1'b0}};
            best_bidx <= {BIDX_W{1'b0}};
            bb_wen <= 1'b0;
            bb_waddr <= {BIDX_W{1'b0}};
            bb_wdata <= {ENTRY_W{1'b0}};
            mb_wen <= 1'b0;
            mb_clr <= 1'b0;
            mb_addr <= {BIDX_W{1'b0}};
            mb_wdata <= 96'h0;
            res_wen <= 1'b0;
            res_addr <= {PIDX_W{1'b0}};
            res_wdata <= {(96+PIDX_W){1'b0}};
        end else begin
            bb_wen <= 1'b0;
            mb_wen <= 1'b0;
            mb_clr <= 1'b0;
            res_wen <= 1'b0;

            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        busy <= 1'b1;
                        cnt <= {{(PIDX_W-1){1'b0}},1'b1};
                        winner_bidx <= {BIDX_W{1'b0}};
                        sx <= p0x; sy <= p0y; sz <= p0z;
                        res_wen <= 1'b1;
                        res_addr <= {PIDX_W{1'b0}};
                        res_wdata <= {p0idx, p0z, p0y, p0x};
                        state <= S_INITP0;
                    end
                end

                S_INITP0: begin
                    if (cnt >= sample_n)
                        state <= S_DONE;
                    else
                        state <= S_ITERINIT;
                end

                S_ITERINIT: begin
                    travel_pos <= {(BIDX_W+1){1'b0}};
                    issued_cnt <= {(BIDX_W+1){1'b0}};
                    collect_cnt <= {(BIDX_W+1){1'b0}};
                    best_valid <= 1'b0;
                    best_dist <= 32'h0;
                    first_iter <= (cnt == {{(PIDX_W-1){1'b0}},1'b1});
                    state <= S_FETCH;
                end

                S_FETCH: begin
                    // bucket_cd captures the addressed entry on this edge.
                    state <= S_WAIT_CD;
                end

                S_WAIT_CD: begin
                    if (cd_out_valid) begin
                        pend_entry <= cd_out_meta[0 +:ENTRY_W];
                        pend_bid <= cd_out_meta[ENTRY_W +:BIDX_W];
                        pend_dlb <= cd_dlb;
                        pend_d <= cd_d;
                        state <= S_ACTION;
                    end
                end

                S_ACTION: begin
                    if (act_issue) begin
                        if (!bkt_fifo_full) begin
                            issued_cnt <= issued_cnt + 1'b1;
                            state <= S_NEXT;
                        end
                    end else if (act_defer) begin
                        mb_wen <= 1'b1;
                        mb_addr <= pend_bid;
                        mb_wdata <= {sz, sy, sx};
                        bb_wen <= 1'b1;
                        bb_waddr <= pend_bid;
                        bb_wdata <= defer_entry;
                        if (take_pending) begin
                            best_valid <= 1'b1;
                            best_x <= pend_fx; best_y <= pend_fy;
                            best_z <= pend_fz; best_dist <= pend_fdist;
                            best_idx <= pend_fidx; best_bidx <= pend_bid;
                        end
                        state <= S_NEXT;
                    end else begin
                        // Implicit skip keeps the bucket far point unchanged.
                        if (take_pending) begin
                            best_valid <= 1'b1;
                            best_x <= pend_fx; best_y <= pend_fy;
                            best_z <= pend_fz; best_dist <= pend_fdist;
                            best_idx <= pend_fidx; best_bidx <= pend_bid;
                        end
                        state <= S_NEXT;
                    end
                end

                S_NEXT: begin
                    if (travel_pos + 1'b1 >= bucket_count) begin
                        state <= S_TDONE;
                    end else begin
                        travel_pos <= travel_pos + 1'b1;
                        state <= S_FETCH;
                    end
                end

                S_TDONE: begin
                    if (issued_cnt == {(BIDX_W+1){1'b0}})
                        state <= S_ITEREND;
                    else
                        state <= S_COLLECT;
                end

                S_COLLECT: begin
                    if (!fp_rd_empty) begin
                        bb_wen <= 1'b1;
                        bb_waddr <= nf_bid;
                        bb_wdata <= collect_entry;
                        mb_clr <= 1'b1;
                        mb_addr <= nf_bid;
                        if (take_return) begin
                            best_valid <= 1'b1;
                            best_x <= nf_x; best_y <= nf_y; best_z <= nf_z;
                            best_dist <= nf_dist;
                            best_idx <= nf_idx;
                            best_bidx <= nf_bid;
                        end
                        collect_cnt <= collect_cnt + 1'b1;
                        if (collect_cnt + 1'b1 >= issued_cnt)
                            state <= S_ITEREND;
                    end
                end

                S_ITEREND: begin
                    res_wen <= 1'b1;
                    res_addr <= cnt;
                    res_wdata <= {best_idx, best_z, best_y, best_x};
                    sx <= best_x; sy <= best_y; sz <= best_z;
                    winner_bidx <= best_bidx;
                    if (cnt + 1'b1 >= sample_n) begin
                        state <= S_DONE;
                    end else begin
                        cnt <= cnt + 1'b1;
                        state <= S_ITERINIT;
                    end
                end

                S_DONE: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    if (!start)
                        state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

    // synopsys translate_off
    always @(posedge clk) begin
        if (busy && state == S_ACTION && act_issue && bkt_fifo_full)
            $display("bucket_engine: safely stalled on full bucket FIFO");
        if (state == S_ITEREND && !best_valid)
            $fatal(1, "bucket_engine: iteration ended without a valid far point");
    end
    // synopsys translate_on
endmodule
