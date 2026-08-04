module bucket_decision_pipe #(
    parameter BIDX_W = 9,
    parameter PIDX_W = 18,
    parameter MCNT_W = 8,
    parameter ENTRY_W = 368 + PIDX_W + MCNT_W,
    parameter FIFO_DEPTH = 8,
    parameter CREDIT_W = $clog2(FIFO_DEPTH + 1),
    parameter OUT_W = 2 + 32 + 32 + 1 + BIDX_W + ENTRY_W
)(
    input  wire                    clk,
    input  wire                    rst_n,

    input  wire                    in_valid,
    output wire                    in_ready,
    input  wire [BIDX_W-1:0]       in_bid,
    input  wire [ENTRY_W-1:0]      in_entry,
    input  wire                    in_first_iter,
    input  wire [31:0]             sample_x,
    input  wire [31:0]             sample_y,
    input  wire [31:0]             sample_z,

    output wire                    out_valid,
    input  wire                    out_ready,
    output wire [1:0]              out_action,
    output wire [BIDX_W-1:0]       out_bid,
    output wire [ENTRY_W-1:0]      out_entry,
    output wire [31:0]             out_dlb,
    output wire [31:0]             out_far_distance
);
    localparam E_MINX=0, E_MINY=32, E_MINZ=64;
    localparam E_MAXX=96, E_MAXY=128, E_MAXZ=160;
    localparam E_FX=240, E_FY=272, E_FZ=304, E_FDIST=336;
    localparam META_W = 1 + BIDX_W + ENTRY_W;
    localparam ACTION_SKIP  = 2'd0;
    localparam ACTION_DEFER = 2'd1;
    localparam ACTION_ISSUE = 2'd2;

    reg [CREDIT_W-1:0] reserved;
    wire input_fire = in_valid && in_ready;
    wire output_fire = out_valid && out_ready;
    assign in_ready = reserved < FIFO_DEPTH;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reserved <= {CREDIT_W{1'b0}};
        end else begin
            case ({input_fire, output_fire})
                2'b10: reserved <= reserved + 1'b1;
                2'b01: reserved <= reserved - 1'b1;
                default: reserved <= reserved;
            endcase
        end
    end

    wire cd_valid;
    wire [META_W-1:0] cd_meta;
    wire [31:0] cd_dlb;
    wire [31:0] cd_far_distance;
    bucket_cd #(.META_W(META_W)) u_bucket_cd (
        .clk(clk), .rst_n(rst_n),
        .in_valid(input_fire),
        .meta_in({in_first_iter, in_bid, in_entry}),
        .qx(sample_x), .qy(sample_y), .qz(sample_z),
        .minx(in_entry[E_MINX +:32]),
        .miny(in_entry[E_MINY +:32]),
        .minz(in_entry[E_MINZ +:32]),
        .maxx(in_entry[E_MAXX +:32]),
        .maxy(in_entry[E_MAXY +:32]),
        .maxz(in_entry[E_MAXZ +:32]),
        .fpx(in_entry[E_FX +:32]),
        .fpy(in_entry[E_FY +:32]),
        .fpz(in_entry[E_FZ +:32]),
        .out_valid(cd_valid), .out_meta(cd_meta),
        .out_dlb(cd_dlb), .out_d(cd_far_distance)
    );

    wire [ENTRY_W-1:0] decision_entry = cd_meta[0 +:ENTRY_W];
    wire [BIDX_W-1:0] decision_bid = cd_meta[ENTRY_W +:BIDX_W];
    wire decision_first_iter = cd_meta[ENTRY_W+BIDX_W];
    wire [31:0] decision_fdist = decision_entry[E_FDIST +:32];
    wire do_issue, do_defer, do_skip;
    bucket_ib u_bucket_ib (
        .valid(cd_valid),
        .first_iter(decision_first_iter),
        .fdist(decision_fdist),
        .dlb(cd_dlb),
        .d(cd_far_distance),
        .do_issue(do_issue),
        .do_defer(do_defer),
        .do_skip(do_skip)
    );
    wire [1:0] decision_action = do_issue ? ACTION_ISSUE :
                                 do_defer ? ACTION_DEFER : ACTION_SKIP;

    wire fifo_full, fifo_empty;
    wire [OUT_W-1:0] fifo_rdata;
    wire [OUT_W-1:0] fifo_wdata = {
        decision_action,
        cd_far_distance,
        cd_dlb,
        decision_first_iter,
        decision_bid,
        decision_entry
    };
    sync_fifo #(.W(OUT_W), .DEPTH(FIFO_DEPTH)) u_decision_fifo (
        .clk(clk), .rst_n(rst_n),
        .wen(cd_valid), .wdata(fifo_wdata), .full(fifo_full),
        .ren(output_fire), .rdata(fifo_rdata), .empty(fifo_empty)
    );

    assign out_valid = !fifo_empty;
    assign out_entry = fifo_rdata[0 +:ENTRY_W];
    assign out_bid = fifo_rdata[ENTRY_W +:BIDX_W];
    assign out_dlb = fifo_rdata[ENTRY_W+BIDX_W+1 +:32];
    assign out_far_distance = fifo_rdata[ENTRY_W+BIDX_W+1+32 +:32];
    assign out_action = fifo_rdata[ENTRY_W+BIDX_W+1+64 +:2];

    // synopsys translate_off
    initial begin
        if (FIFO_DEPTH < 4)
            $fatal(1, "bucket_decision_pipe: FIFO_DEPTH should cover the four-stage CD pipe");
        if ((FIFO_DEPTH & (FIFO_DEPTH-1)) != 0)
            $fatal(1, "bucket_decision_pipe: sync_fifo requires power-of-two depth");
    end
    always @(posedge clk) begin
        if (cd_valid && fifo_full)
            $fatal(1, "bucket_decision_pipe: credit invariant violated");
        if (reserved > FIFO_DEPTH)
            $fatal(1, "bucket_decision_pipe: reserved credit overflow");
        if (do_skip && do_defer)
            $fatal(1, "bucket_decision_pipe: invalid dual decision");
    end
    // synopsys translate_on
endmodule
