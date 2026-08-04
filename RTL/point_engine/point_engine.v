module point_engine #(
    parameter L      = 4,
    parameter R      = 4,
    parameter LIDX_W = 11
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               clr,
    input  wire [L-1:0]       m_load,
    input  wire [L*32-1:0]    m_x,
    input  wire [L*32-1:0]    m_y,
    input  wire [L*32-1:0]    m_z,
    input  wire [R-1:0]       in_valid,
    input  wire [R*LIDX_W-1:0] in_idx,
    input  wire [R*32-1:0]    in_x,
    input  wire [R*32-1:0]    in_y,
    input  wire [R*32-1:0]    in_z,
    input  wire [R*32-1:0]    in_dist,
    output reg  [LIDX_W-1:0]  far_idx,
    output reg  [31:0]        far_dist,
    output reg                far_valid,
    output wire [R-1:0]        o_row_valid,
    output wire [R*LIDX_W-1:0] o_row_idx,
    output wire [R*32-1:0]     o_row_dist
);
    wire               row_valid [0:R-1];
    wire [LIDX_W-1:0]  row_idx   [0:R-1];
    wire [31:0]        row_dist  [0:R-1];
    genvar r;
    generate for (r = 0; r < R; r = r + 1) begin : g_row
        pe_row #(.L(L), .LIDX_W(LIDX_W)) u_row (
            .clk(clk), .rst_n(rst_n), .m_load(m_load), .m_x(m_x), .m_y(m_y), .m_z(m_z),
            .in_valid(in_valid[r]), .in_idx(in_idx[r*LIDX_W +: LIDX_W]),
            .in_x(in_x[r*32 +: 32]), .in_y(in_y[r*32 +: 32]), .in_z(in_z[r*32 +: 32]), .in_dist(in_dist[r*32 +: 32]),
            .out_valid(row_valid[r]), .out_idx(row_idx[r]), .out_x(), .out_y(), .out_z(), .out_dist(row_dist[r])
        );
    end endgenerate
    genvar gr;
    generate for (gr = 0; gr < R; gr = gr + 1) begin : g_expose
        assign o_row_valid[gr]                = row_valid[gr];
        assign o_row_idx[gr*LIDX_W +: LIDX_W] = row_idx[gr];
        assign o_row_dist[gr*32 +: 32]        = row_dist[gr];
    end endgenerate

    reg               best_valid;
    reg [LIDX_W-1:0]  best_idx;
    reg [31:0]        best_dist;
    integer k;
    always @* begin
        best_valid = 1'b0;
        best_idx   = {LIDX_W{1'b0}};
        best_dist  = 32'h0;
        for (k = 0; k < R; k = k + 1) begin
            if (row_valid[k] && (!best_valid || (row_dist[k][30:0] > best_dist[30:0]))) begin
                best_valid = 1'b1;
                best_idx   = row_idx[k];
                best_dist  = row_dist[k];
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            far_dist  <= 32'h0;
            far_idx   <= {LIDX_W{1'b0}};
            far_valid <= 1'b0;
        end else if (clr) begin
            far_dist  <= 32'h0;
            far_idx   <= {LIDX_W{1'b0}};
            far_valid <= 1'b0;
        end else if (best_valid && (!far_valid || (best_dist[30:0] > far_dist[30:0]))) begin
            far_dist  <= best_dist;
            far_idx   <= best_idx;
            far_valid <= 1'b1;
        end
    end
endmodule
