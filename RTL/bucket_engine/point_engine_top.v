module point_engine_top #(
    parameter L      = 4,
    parameter R      = 4,
    parameter LIDX_W = 11,
    parameter BIDX_W = 9,
    parameter PIDX_W = 18,
    parameter NUMP_W = 16,
    parameter ADDR_W = 32,
    parameter MCNT_W = 8,
    parameter BF_W   = BIDX_W + ADDR_W + NUMP_W + 96 + MCNT_W,
    parameter FP_W   = BIDX_W + 96 + 32 + PIDX_W
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               bkt_empty,
    input  wire [BF_W-1:0]    bkt_rdata,
    output wire               bkt_ren,
    input  wire               fp_full,
    output wire               fp_wen,
    output wire [FP_W-1:0]    fp_wdata,
    output wire [BIDX_W-1:0]  mb_bid,
    output wire [7:0]         mb_k,
    input  wire [95:0]        mb_rdata,
    output wire [PIDX_W-1:0]  co_addr,
    input  wire [R*96-1:0]    co_rdata,
    output wire [PIDX_W-1:0]  di_raddr,
    input  wire [R*32-1:0]    di_rdata,
    output wire [R-1:0]       di_wstrb,
    output wire [PIDX_W-1:0]  di_waddr,
    output wire [R*32-1:0]    di_wdata
);
    localparam [31:0] INF32 = 32'h7F80_0000;
    localparam integer R_LOG2 = $clog2(R);
    localparam integer C_W = (L <= 1) ? 1 : $clog2(L);
    localparam OFF_SX = BIDX_W + ADDR_W + NUMP_W;

    wire [BIDX_W-1:0] bf_bid  = bkt_rdata[0 +: BIDX_W];
    wire [ADDR_W-1:0] bf_ptr  = bkt_rdata[BIDX_W +: ADDR_W];
    wire [NUMP_W-1:0] bf_nump = bkt_rdata[BIDX_W+ADDR_W +: NUMP_W];
    wire [31:0]       bf_sx   = bkt_rdata[OFF_SX    +: 32];
    wire [31:0]       bf_sy   = bkt_rdata[OFF_SX+32 +: 32];
    wire [31:0]       bf_sz   = bkt_rdata[OFF_SX+64 +: 32];
    wire [MCNT_W-1:0] bf_mcnt = bkt_rdata[OFF_SX+96 +: MCNT_W];

    localparam T_IDLE=0, T_LDMERGE=1, T_STREAM=2, T_COLLECT=3, T_PUSH=4;
    reg [2:0]         st;
    reg [BIDX_W-1:0]  r_bid;
    reg [PIDX_W-1:0]  r_base;
    reg [NUMP_W-1:0]  r_nump;
    reg [31:0]        r_sx, r_sy, r_sz;
    reg [7:0]         r_npass, pass;
    reg [NUMP_W-1:0]  r_nbatch;
    reg [C_W-1:0]     c;
    reg [NUMP_W-1:0]  in_batch, cap_batch;
    reg [FP_W-1:0]    fp_hold;
    reg [7:0]         r_mcnt_ext;

    wire last_pass = (pass == r_npass - 8'd1);
    assign bkt_ren = (st == T_IDLE) && !bkt_empty;

    wire [L*32-1:0]      m_x, m_y, m_z;
    wire [R*LIDX_W-1:0]  in_idx;
    wire [R*32-1:0]      in_x, in_y, in_z, in_dist;
    wire [R-1:0]         in_valid;
    wire [LIDX_W-1:0]    far_idx;
    wire [31:0]          far_dist;
    wire                 far_valid;
    wire [R-1:0]         o_row_valid;
    wire [R*LIDX_W-1:0]  o_row_idx;
    wire [R*32-1:0]      o_row_dist;

    wire [7:0] refi = pass * L + c;
    wire [95:0] merge_pt = (refi < r_mcnt_ext) ? mb_rdata :
                           (refi == r_mcnt_ext) ? {r_sz, r_sy, r_sx} :
                                                 {INF32, INF32, INF32};
    assign mb_bid = r_bid;
    assign mb_k   = refi;
    assign m_x    = {L{merge_pt[31:0]}};
    assign m_y    = {L{merge_pt[63:32]}};
    assign m_z    = {L{merge_pt[95:64]}};

    // Intermediate merge passes only update MDT.  Clear the registered max
    // tree while loading the first reference of the final pass so only final
    // MDT values participate in bucket-far-point selection.
    wire clr = (st == T_LDMERGE) && last_pass && (c == {C_W{1'b0}});
    wire [L-1:0] m_load = (st == T_LDMERGE) ?
                          ({{(L-1){1'b0}}, 1'b1} << c) :
                          {L{1'b0}};

    wire streaming = (st == T_STREAM) && (in_batch < r_nbatch);
    // Address generation must use PIDX_W rather than NUMP_W: the local point
    // count may be 16 bits while the reordered global point address is 18 bits.
    wire [PIDX_W:0] batch_base_ext = in_batch * R;
    wire [PIDX_W-1:0] stream_addr =
        r_base + batch_base_ext[PIDX_W-1:0];
    wire [PIDX_W-1:0] far_word_base =
        r_base + ((far_idx >> R_LOG2) << R_LOG2);

    assign co_addr  = (st == T_COLLECT) ? far_word_base : stream_addr;
    assign di_raddr = stream_addr;

    genvar g;
    generate
        for (g = 0; g < R; g = g + 1) begin : g_lane
            wire [PIDX_W:0] lane_pos = batch_base_ext + g;
            assign in_idx[g*LIDX_W +: LIDX_W] = lane_pos[LIDX_W-1:0];
            assign in_x[g*32 +: 32] = co_rdata[g*96      +: 32];
            assign in_y[g*32 +: 32] = co_rdata[g*96 + 32 +: 32];
            assign in_z[g*32 +: 32] = co_rdata[g*96 + 64 +: 32];
            assign in_dist[g*32 +: 32] = di_rdata[g*32 +: 32];
            assign in_valid[g] = streaming &&
                                 (lane_pos < {{(PIDX_W+1-NUMP_W){1'b0}}, r_nump});
        end
    endgenerate

    assign di_wstrb = (st == T_STREAM) ? o_row_valid : {R{1'b0}};
    assign di_waddr = r_base + o_row_idx[0 +: LIDX_W];
    assign di_wdata = o_row_dist;

    wire [R_LOG2-1:0] far_off = far_idx[R_LOG2-1:0];
    wire [95:0] far_co = co_rdata[far_off*96 +: 96];

    assign fp_wen   = (st == T_PUSH) && !fp_full;
    assign fp_wdata = fp_hold;

    point_engine #(.L(L), .R(R), .LIDX_W(LIDX_W)) u_pe (
        .clk(clk),
        .rst_n(rst_n),
        .clr(clr),
        .m_load(m_load),
        .m_x(m_x),
        .m_y(m_y),
        .m_z(m_z),
        .in_valid(in_valid),
        .in_idx(in_idx),
        .in_x(in_x),
        .in_y(in_y),
        .in_z(in_z),
        .in_dist(in_dist),
        .far_idx(far_idx),
        .far_dist(far_dist),
        .far_valid(far_valid),
        .o_row_valid(o_row_valid),
        .o_row_idx(o_row_idx),
        .o_row_dist(o_row_dist)
    );

    wire any_row_valid = |o_row_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st          <= T_IDLE;
            r_bid       <= {BIDX_W{1'b0}};
            r_base      <= {PIDX_W{1'b0}};
            r_nump      <= {NUMP_W{1'b0}};
            r_sx        <= 32'h0;
            r_sy        <= 32'h0;
            r_sz        <= 32'h0;
            r_npass     <= 8'd0;
            pass        <= 8'd0;
            r_nbatch    <= {NUMP_W{1'b0}};
            c           <= {C_W{1'b0}};
            in_batch    <= {NUMP_W{1'b0}};
            cap_batch   <= {NUMP_W{1'b0}};
            fp_hold     <= {FP_W{1'b0}};
            r_mcnt_ext  <= 8'd0;
        end else begin
            case (st)
                T_IDLE: begin
                    if (!bkt_empty) begin
                        if (bf_nump == {NUMP_W{1'b0}}) begin
                            // CPU preprocessing should never create empty
                            // leaves, but avoid a functional-model deadlock.
                            fp_hold <= {bf_bid, {PIDX_W{1'b0}},
                                        32'h0000_0000, 96'h0};
                            st <= T_PUSH;
                        end else begin
                            r_bid  <= bf_bid;
                            r_base <= bf_ptr[PIDX_W-1:0];
                            r_nump <= bf_nump;
                            r_sx   <= bf_sx;
                            r_sy   <= bf_sy;
                            r_sz   <= bf_sz;
                            r_mcnt_ext <= {{(8-MCNT_W){1'b0}}, bf_mcnt};
                            r_npass <= (({{(8-MCNT_W){1'b0}}, bf_mcnt} +
                                         8'd1 + L - 1) / L);
                            // Ceiling division preserves the 1..R-1 tail
                            // points that floor division previously dropped.
                            r_nbatch <= (bf_nump + R - 1) / R;
                            pass <= 8'd0;
                            c <= {C_W{1'b0}};
                            st <= T_LDMERGE;
                        end
                    end
                end

                T_LDMERGE: begin
                    if (c == L-1) begin
                        in_batch  <= {NUMP_W{1'b0}};
                        cap_batch <= {NUMP_W{1'b0}};
                        st <= T_STREAM;
                    end else begin
                        c <= c + {{(C_W-1){1'b0}}, 1'b1};
                    end
                end

                T_STREAM: begin
                    if (in_batch < r_nbatch)
                        in_batch <= in_batch + {{(NUMP_W-1){1'b0}}, 1'b1};

                    if (any_row_valid)
                        cap_batch <= cap_batch + {{(NUMP_W-1){1'b0}}, 1'b1};

                    if ((cap_batch + (any_row_valid ? 1'b1 : 1'b0)) >=
                        r_nbatch) begin
                        if (last_pass) begin
                            st <= T_COLLECT;
                        end else begin
                            pass <= pass + 8'd1;
                            c <= {C_W{1'b0}};
                            st <= T_LDMERGE;
                        end
                    end
                end

                T_COLLECT: begin
                    if (far_valid) begin
                        fp_hold <= {r_bid, r_base + far_idx,
                                    far_dist, far_co};
                        st <= T_PUSH;
                    end
                end

                T_PUSH: begin
                    if (!fp_full)
                        st <= T_IDLE;
                end

                default: st <= T_IDLE;
            endcase
        end
    end

    // synopsys translate_off
    initial begin
        if (R != 4)
            $fatal(1, "point_engine_top: current memory packing requires R=4");
        if ((R & (R-1)) != 0)
            $fatal(1, "point_engine_top: R must be a power of two");
        if (L > 16)
            $fatal(1, "point_engine_top: merge loader supports L<=16");
        if (PIDX_W + 1 < NUMP_W)
            $fatal(1, "point_engine_top: PIDX_W must cover NUMP_W");
    end
    // synopsys translate_on
endmodule
