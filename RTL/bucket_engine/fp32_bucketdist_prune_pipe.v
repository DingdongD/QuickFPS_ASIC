module fp32_bucketdist_prune_pipe #(
    parameter RID_W = 9,
    parameter META_W = RID_W
)(
    input  wire              clk,
    input  wire              rst_n,
    input  wire              in_valid,
    input  wire [META_W-1:0] meta_in,
    input  wire [31:0]       qx,
    input  wire [31:0]       qy,
    input  wire [31:0]       qz,
    input  wire [31:0]       minx,
    input  wire [31:0]       miny,
    input  wire [31:0]       minz,
    input  wire [31:0]       maxx,
    input  wire [31:0]       maxy,
    input  wire [31:0]       maxz,
    input  wire [31:0]       t_region,
    input  wire              no_skip,
    output reg               out_valid,
    output reg [META_W-1:0]  out_meta,
    output reg [31:0]        out_dlb,
    output reg               out_skip
);
    wire [31:0] gx, gy, gz;
    wire [31:0] gx2, gy2, gz2;

    fp32_box_gap u_gx (.q(qx), .bmin(minx), .bmax(maxx), .gap(gx));
    fp32_box_gap u_gy (.q(qy), .bmin(miny), .bmax(maxy), .gap(gy));
    fp32_box_gap u_gz (.q(qz), .bmin(minz), .bmax(maxz), .gap(gz));

    fp32_mul u_gx2 (.a(gx), .b(gx), .result(gx2));
    fp32_mul u_gy2 (.a(gy), .b(gy), .result(gy2));
    fp32_mul u_gz2 (.a(gz), .b(gz), .result(gz2));

    reg              v1;
    reg [META_W-1:0] meta1;
    reg [31:0]       gx2_r, gy2_r, gz2_r;
    reg [31:0]       t_region_r;
    reg              no_skip_r;

    wire [31:0] sum_xy;
    fp32_add u_sum_xy (.a(gx2_r),  .b(gy2_r), .result(sum_xy));

    reg              v2;
    reg [META_W-1:0] meta2;
    reg [31:0]       sum_xy_r, gz2_rr;
    reg [31:0]       t_region_rr;
    reg              no_skip_rr;

    wire [31:0] dlb_next;
    fp32_add u_sum_z  (.a(sum_xy_r), .b(gz2_rr), .result(dlb_next));

    wire skip_next = (!no_skip_rr) && (dlb_next[30:0] > t_region_rr[30:0]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1 <= 1'b0;
            meta1 <= {META_W{1'b0}};
            gx2_r <= 32'b0;
            gy2_r <= 32'b0;
            gz2_r <= 32'b0;
            t_region_r <= 32'b0;
            no_skip_r <= 1'b0;
            v2 <= 1'b0;
            meta2 <= {META_W{1'b0}};
            sum_xy_r <= 32'b0;
            gz2_rr <= 32'b0;
            t_region_rr <= 32'b0;
            no_skip_rr <= 1'b0;
            out_valid <= 1'b0;
            out_meta <= {META_W{1'b0}};
            out_dlb <= 32'b0;
            out_skip <= 1'b0;
        end else begin
            v1 <= in_valid;
            meta1 <= meta_in;
            gx2_r <= gx2;
            gy2_r <= gy2;
            gz2_r <= gz2;
            t_region_r <= t_region;
            no_skip_r <= no_skip;

            v2 <= v1;
            meta2 <= meta1;
            sum_xy_r <= sum_xy;
            gz2_rr <= gz2_r;
            t_region_rr <= t_region_r;
            no_skip_rr <= no_skip_r;

            out_valid <= v2;
            out_meta <= meta2;
            out_dlb <= dlb_next;
            out_skip <= skip_next;
        end
    end
endmodule
