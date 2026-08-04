module fp32_box_gap (
    input  wire [31:0] q,
    input  wire [31:0] bmin,
    input  wire [31:0] bmax,
    output wire [31:0] gap
);
    wire q_lt_min = (q[31] != bmin[31]) ? q[31] : (q[30:0] < bmin[30:0]);
    wire q_gt_max = (q[31] != bmax[31]) ? bmax[31] : (q[30:0] > bmax[30:0]);

    wire [31:0] min_minus_q;
    wire [31:0] q_minus_max;

    fp32_sub u_min_sub_q (.a(bmin), .b(q),    .result(min_minus_q));
    fp32_sub u_q_sub_max (.a(q),    .b(bmax), .result(q_minus_max));

    assign gap = q_lt_min ? min_minus_q :
                 q_gt_max ? q_minus_max :
                            32'h0000_0000;
endmodule
