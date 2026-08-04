module point_engine #(
    parameter L      = 4,
    parameter R      = 4,
    parameter LIDX_W = 11
)(
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 clr,
    input  wire [L-1:0]         m_load,
    input  wire [L*32-1:0]      m_x,
    input  wire [L*32-1:0]      m_y,
    input  wire [L*32-1:0]      m_z,
    input  wire [R-1:0]         in_valid,
    input  wire [R*LIDX_W-1:0]  in_idx,
    input  wire [R*32-1:0]      in_x,
    input  wire [R*32-1:0]      in_y,
    input  wire [R*32-1:0]      in_z,
    input  wire [R*32-1:0]      in_dist,
    output wire [LIDX_W-1:0]    far_idx,
    output wire [31:0]          far_dist,
    output wire                 far_valid,
    output wire [R-1:0]         o_row_valid,
    output wire [R*LIDX_W-1:0]  o_row_idx,
    output wire [R*32-1:0]      o_row_dist
);
    wire              row_valid [0:R-1];
    wire [LIDX_W-1:0] row_idx   [0:R-1];
    wire [31:0]       row_dist  [0:R-1];

    genvar r;
    generate
        for (r = 0; r < R; r = r + 1) begin : g_row
            pe_row #(.L(L), .LIDX_W(LIDX_W)) u_row (
                .clk(clk),
                .rst_n(rst_n),
                .m_load(m_load),
                .m_x(m_x),
                .m_y(m_y),
                .m_z(m_z),
                .in_valid(in_valid[r]),
                .in_idx(in_idx[r*LIDX_W +: LIDX_W]),
                .in_x(in_x[r*32 +: 32]),
                .in_y(in_y[r*32 +: 32]),
                .in_z(in_z[r*32 +: 32]),
                .in_dist(in_dist[r*32 +: 32]),
                .out_valid(row_valid[r]),
                .out_idx(row_idx[r]),
                .out_x(),
                .out_y(),
                .out_z(),
                .out_dist(row_dist[r])
            );
        end
    endgenerate

    genvar gr;
    generate
        for (gr = 0; gr < R; gr = gr + 1) begin : g_expose
            assign o_row_valid[gr]                  = row_valid[gr];
            assign o_row_idx[gr*LIDX_W +: LIDX_W] = row_idx[gr];
            assign o_row_dist[gr*32 +: 32]         = row_dist[gr];
        end
    endgenerate

    // The paper configuration is a 4x4 PE array.  Keep the reduction as an
    // explicit registered max tree rather than a large combinational for-loop.
    // The tree also accumulates across all point batches of the final merge
    // pass and applies deterministic smaller-index tie-breaking.
    generate
        if (R == 4) begin : g_max_tree4
            max_tree4 #(.LIDX_W(LIDX_W)) u_max_tree (
                .clk(clk),
                .rst_n(rst_n),
                .clr(clr),
                .leaf_valid0(row_valid[0]),
                .leaf_idx0(row_idx[0]),
                .leaf_dist0(row_dist[0]),
                .leaf_valid1(row_valid[1]),
                .leaf_idx1(row_idx[1]),
                .leaf_dist1(row_dist[1]),
                .leaf_valid2(row_valid[2]),
                .leaf_idx2(row_idx[2]),
                .leaf_dist2(row_dist[2]),
                .leaf_valid3(row_valid[3]),
                .leaf_idx3(row_idx[3]),
                .leaf_dist3(row_dist[3]),
                .far_idx(far_idx),
                .far_dist(far_dist),
                .far_valid(far_valid)
            );
        end else begin : g_unsupported_rows
            // The complete functional core intentionally fixes R=4 to match
            // the QuickFPS paper and the existing synthesized 4x4 datapath.
            assign far_idx   = {LIDX_W{1'b0}};
            assign far_dist  = 32'h0000_0000;
            assign far_valid = 1'b0;
        end
    endgenerate

    // synopsys translate_off
    initial begin
        if (R != 4)
            $fatal(1, "point_engine: functional core currently requires R=4");
    end
    // synopsys translate_on
endmodule
