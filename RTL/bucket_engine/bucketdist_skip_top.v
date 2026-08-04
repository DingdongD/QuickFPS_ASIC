module bucketdist_skip_top #(
    parameter RID_W = 10
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               req_valid,
    input  wire [RID_W-1:0]   req_rid,
    input  wire [31:0]        qx, qy, qz,
    input  wire               first_sample,
    output wire [RID_W-1:0]   rd_rid,
    input  wire [31:0]        box_minx, box_miny, box_minz,
    input  wire [31:0]        box_maxx, box_maxy, box_maxz,
    input  wire [31:0]        treg_max,
    output wire               res_valid,
    output wire [RID_W-1:0]   res_rid,
    output wire [31:0]        res_dlb,
    output wire               res_skip,
    output wire               res_fetch
);
    assign rd_rid = req_rid;
    wire              pv, ps;
    wire [RID_W-1:0]  pr;
    wire [31:0]       pd;
    fp32_bucketdist_prune_pipe #(.RID_W(RID_W), .META_W(RID_W)) u_prune (
        .clk(clk), .rst_n(rst_n), .in_valid(req_valid), .meta_in(req_rid),
        .qx(qx), .qy(qy), .qz(qz),
        .minx(box_minx), .miny(box_miny), .minz(box_minz),
        .maxx(box_maxx), .maxy(box_maxy), .maxz(box_maxz),
        .t_region(treg_max), .no_skip(first_sample),
        .out_valid(pv), .out_meta(pr), .out_dlb(pd), .out_skip(ps)
    );
    assign res_valid = pv;
    assign res_rid   = pr;
    assign res_dlb   = pd;
    assign res_skip  = ps;
    assign res_fetch = pv & ~ps;
endmodule
