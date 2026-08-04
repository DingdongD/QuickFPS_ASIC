`timescale 1ns/1ps
module tb_max_tree4_tie;
    localparam LIDX_W = 11;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg clr = 1'b0;
    reg v0=0, v1=0, v2=0, v3=0;
    reg [LIDX_W-1:0] i0=0, i1=0, i2=0, i3=0;
    reg [31:0] d0=0, d1=0, d2=0, d3=0;
    wire [LIDX_W-1:0] far_idx;
    wire [31:0] far_dist;
    wire far_valid;

    max_tree4 #(.LIDX_W(LIDX_W)) dut (
        .clk(clk), .rst_n(rst_n), .clr(clr),
        .leaf_valid0(v0), .leaf_idx0(i0), .leaf_dist0(d0),
        .leaf_valid1(v1), .leaf_idx1(i1), .leaf_dist1(d1),
        .leaf_valid2(v2), .leaf_idx2(i2), .leaf_dist2(d2),
        .leaf_valid3(v3), .leaf_idx3(i3), .leaf_dist3(d3),
        .far_idx(far_idx), .far_dist(far_dist), .far_valid(far_valid)
    );

    task check_far;
        input expected_valid;
        input [LIDX_W-1:0] expected_idx;
        input [31:0] expected_dist;
        begin
            #1;
            if (far_valid !== expected_valid ||
                (expected_valid &&
                 (far_idx !== expected_idx || far_dist !== expected_dist))) begin
                $display("MAX_TREE_FAIL valid=%0d idx=%0d dist=%08x expected valid=%0d idx=%0d dist=%08x",
                         far_valid, far_idx, far_dist,
                         expected_valid, expected_idx, expected_dist);
                $fatal(1);
            end
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        check_far(1'b0, 0, 0);

        // Two leaves have the same maximum distance.  Smaller index wins.
        v0<=1; i0<=11'd7; d0<=32'h4080_0000; // 4.0
        v1<=1; i1<=11'd9; d1<=32'h4110_0000; // 9.0
        v2<=1; i2<=11'd3; d2<=32'h4110_0000; // 9.0
        v3<=1; i3<=11'd1; d3<=32'h3f80_0000; // 1.0
        @(posedge clk);
        check_far(1'b1, 11'd3, 32'h4110_0000);

        // Accumulation across cycles must also apply deterministic ties.
        v0<=1; i0<=11'd2; d0<=32'h4110_0000;
        v1<=1; i1<=11'd6; d1<=32'h4100_0000;
        v2<=0; v3<=0;
        @(posedge clk);
        check_far(1'b1, 11'd2, 32'h4110_0000);

        // Lower candidates do not replace the accumulated maximum.
        v0<=1; i0<=11'd0; d0<=32'h4000_0000;
        v1<=0; v2<=0; v3<=0;
        @(posedge clk);
        check_far(1'b1, 11'd2, 32'h4110_0000);

        clr<=1; v0<=0;
        @(posedge clk);
        clr<=0;
        check_far(1'b0, 0, 0);

        v3<=1; i3<=11'd5; d3<=32'h4000_0000;
        @(posedge clk);
        check_far(1'b1, 11'd5, 32'h4000_0000);

        $display("MAX_TREE_PASS");
        $finish;
    end
endmodule
