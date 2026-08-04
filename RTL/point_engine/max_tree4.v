module max_tree4 #(
    parameter LIDX_W = 11
)(
    input  wire               clk,
    input  wire               rst_n,
    input  wire               clr,
    input  wire               leaf_valid0,
    input  wire [LIDX_W-1:0]  leaf_idx0,
    input  wire [31:0]        leaf_dist0,
    input  wire               leaf_valid1,
    input  wire [LIDX_W-1:0]  leaf_idx1,
    input  wire [31:0]        leaf_dist1,
    input  wire               leaf_valid2,
    input  wire [LIDX_W-1:0]  leaf_idx2,
    input  wire [31:0]        leaf_dist2,
    input  wire               leaf_valid3,
    input  wire [LIDX_W-1:0]  leaf_idx3,
    input  wire [31:0]        leaf_dist3,
    output reg  [LIDX_W-1:0]  far_idx,
    output reg  [31:0]        far_dist,
    output reg                far_valid
);
    // Squared distances are non-negative finite FP32 values in the
    // functional QuickFPS model.  Comparing bits [30:0] therefore follows
    // numerical order.  Equal distances use the smaller point index so that
    // PE-lane ordering, bucket reordering, and backpressure cannot change the
    // selected FPS sequence.
    function automatic is_better;
        input [31:0]       cand_dist;
        input [LIDX_W-1:0] cand_idx;
        input [31:0]       cur_dist;
        input [LIDX_W-1:0] cur_idx;
        begin
            is_better = (cand_dist[30:0] > cur_dist[30:0]) ||
                        ((cand_dist[30:0] == cur_dist[30:0]) &&
                         (cand_idx < cur_idx));
        end
    endfunction

    wire a_pick1 = leaf_valid1 &&
                   (!leaf_valid0 ||
                    is_better(leaf_dist1, leaf_idx1,
                              leaf_dist0, leaf_idx0));
    wire a_valid = leaf_valid0 | leaf_valid1;
    wire [31:0]       a_dist = a_pick1 ? leaf_dist1 : leaf_dist0;
    wire [LIDX_W-1:0] a_idx  = a_pick1 ? leaf_idx1  : leaf_idx0;

    wire b_pick3 = leaf_valid3 &&
                   (!leaf_valid2 ||
                    is_better(leaf_dist3, leaf_idx3,
                              leaf_dist2, leaf_idx2));
    wire b_valid = leaf_valid2 | leaf_valid3;
    wire [31:0]       b_dist = b_pick3 ? leaf_dist3 : leaf_dist2;
    wire [LIDX_W-1:0] b_idx  = b_pick3 ? leaf_idx3  : leaf_idx2;

    wire pick_b = b_valid &&
                  (!a_valid || is_better(b_dist, b_idx, a_dist, a_idx));
    wire best_valid = a_valid | b_valid;
    wire [31:0]       best_dist = pick_b ? b_dist : a_dist;
    wire [LIDX_W-1:0] best_idx  = pick_b ? b_idx  : a_idx;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            far_dist  <= 32'h0000_0000;
            far_idx   <= {LIDX_W{1'b0}};
            far_valid <= 1'b0;
        end else if (clr) begin
            far_dist  <= 32'h0000_0000;
            far_idx   <= {LIDX_W{1'b0}};
            far_valid <= 1'b0;
        end else if (best_valid &&
                     (!far_valid ||
                      is_better(best_dist, best_idx, far_dist, far_idx))) begin
            far_dist  <= best_dist;
            far_idx   <= best_idx;
            far_valid <= 1'b1;
        end
    end
endmodule
