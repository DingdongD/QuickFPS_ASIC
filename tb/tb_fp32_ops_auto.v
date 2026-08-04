
`timescale 1ns/1ps
module tb_fp32_ops;
    reg [31:0] a, b;
    wire [31:0] add_y, sub_y, mul_y;
    fp32_add u_add(.a(a), .b(b), .result(add_y));
    fp32_sub u_sub(.a(a), .b(b), .result(sub_y));
    fp32_mul u_mul(.a(a), .b(b), .result(mul_y));
    initial begin

        a = 32'h3fc00000; b = 32'h40000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 0, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 1, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'h00000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 2, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 3, a, b, add_y, sub_y, mul_y);

        a = 32'hbe000000; b = 32'h00000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 4, a, b, add_y, sub_y, mul_y);

        a = 32'h3f000000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 5, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 6, a, b, add_y, sub_y, mul_y);

        a = 32'hbf800000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 7, a, b, add_y, sub_y, mul_y);

        a = 32'hc1000000; b = 32'h40900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 8, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 9, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'h41000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 10, a, b, add_y, sub_y, mul_y);

        a = 32'h41000000; b = 32'hc0500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 11, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 12, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 13, a, b, add_y, sub_y, mul_y);

        a = 32'h3f000000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 14, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'hbfc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 15, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'hbe000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 16, a, b, add_y, sub_y, mul_y);

        a = 32'hbe800000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 17, a, b, add_y, sub_y, mul_y);

        a = 32'h40000000; b = 32'h41800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 18, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'hbfc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 19, a, b, add_y, sub_y, mul_y);

        a = 32'hc1000000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 20, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 21, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'h80000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 22, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 23, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'h80000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 24, a, b, add_y, sub_y, mul_y);

        a = 32'h3fc00000; b = 32'h41000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 25, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'hbf000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 26, a, b, add_y, sub_y, mul_y);

        a = 32'h3e800000; b = 32'hc0000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 27, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 28, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 29, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'hc0000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 30, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 31, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 32, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'h80000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 33, a, b, add_y, sub_y, mul_y);

        a = 32'h41000000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 34, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'hc0000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 35, a, b, add_y, sub_y, mul_y);

        a = 32'hc1000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 36, a, b, add_y, sub_y, mul_y);

        a = 32'hc0500000; b = 32'hc0000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 37, a, b, add_y, sub_y, mul_y);

        a = 32'h40000000; b = 32'hc0500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 38, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 39, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'hbe000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 40, a, b, add_y, sub_y, mul_y);

        a = 32'h41000000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 41, a, b, add_y, sub_y, mul_y);

        a = 32'h41000000; b = 32'h40900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 42, a, b, add_y, sub_y, mul_y);

        a = 32'h3fc00000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 43, a, b, add_y, sub_y, mul_y);

        a = 32'hc1000000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 44, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'h40500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 45, a, b, add_y, sub_y, mul_y);

        a = 32'hbe000000; b = 32'hc0500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 46, a, b, add_y, sub_y, mul_y);

        a = 32'hc0500000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 47, a, b, add_y, sub_y, mul_y);

        a = 32'hbe000000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 48, a, b, add_y, sub_y, mul_y);

        a = 32'h3e800000; b = 32'hbf000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 49, a, b, add_y, sub_y, mul_y);

        a = 32'h3e800000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 50, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 51, a, b, add_y, sub_y, mul_y);

        a = 32'hbe800000; b = 32'hbf000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 52, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'h41000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 53, a, b, add_y, sub_y, mul_y);

        a = 32'hbf000000; b = 32'h3f400000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 54, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 55, a, b, add_y, sub_y, mul_y);

        a = 32'h80000000; b = 32'hc0500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 56, a, b, add_y, sub_y, mul_y);

        a = 32'hbf000000; b = 32'hc0500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 57, a, b, add_y, sub_y, mul_y);

        a = 32'h3fc00000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 58, a, b, add_y, sub_y, mul_y);

        a = 32'hbf000000; b = 32'hbf000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 59, a, b, add_y, sub_y, mul_y);

        a = 32'hbf000000; b = 32'h41000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 60, a, b, add_y, sub_y, mul_y);

        a = 32'hc0500000; b = 32'h41800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 61, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'h40000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 62, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'hc0000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 63, a, b, add_y, sub_y, mul_y);

        a = 32'hbe000000; b = 32'hc0500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 64, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 65, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 66, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 67, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 68, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'h41800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 69, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'h40000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 70, a, b, add_y, sub_y, mul_y);

        a = 32'h3f000000; b = 32'h3f800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 71, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'hc1000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 72, a, b, add_y, sub_y, mul_y);

        a = 32'hbf800000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 73, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'hc1800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 74, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'h40900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 75, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'h40500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 76, a, b, add_y, sub_y, mul_y);

        a = 32'h41000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 77, a, b, add_y, sub_y, mul_y);

        a = 32'hbe800000; b = 32'h41000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 78, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'hbfc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 79, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 80, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'hbe000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 81, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'hbe000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 82, a, b, add_y, sub_y, mul_y);

        a = 32'h3fc00000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 83, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'h40980000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 84, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'h40980000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 85, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'h40000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 86, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 87, a, b, add_y, sub_y, mul_y);

        a = 32'h41800000; b = 32'h40000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 88, a, b, add_y, sub_y, mul_y);

        a = 32'hbf000000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 89, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 90, a, b, add_y, sub_y, mul_y);

        a = 32'hbe800000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 91, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 92, a, b, add_y, sub_y, mul_y);

        a = 32'hbe800000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 93, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'hbf000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 94, a, b, add_y, sub_y, mul_y);

        a = 32'h3fc00000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 95, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'h40500000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 96, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 97, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'h3e000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 98, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 99, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'h3f800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 100, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'h40100000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 101, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 102, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 103, a, b, add_y, sub_y, mul_y);

        a = 32'hbe000000; b = 32'h00000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 104, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'h41000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 105, a, b, add_y, sub_y, mul_y);

        a = 32'hbe000000; b = 32'hbe000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 106, a, b, add_y, sub_y, mul_y);

        a = 32'h80000000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 107, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'h00000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 108, a, b, add_y, sub_y, mul_y);

        a = 32'h3e000000; b = 32'h3f800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 109, a, b, add_y, sub_y, mul_y);

        a = 32'h3e800000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 110, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 111, a, b, add_y, sub_y, mul_y);

        a = 32'h40900000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 112, a, b, add_y, sub_y, mul_y);

        a = 32'h80000000; b = 32'h3e800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 113, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 114, a, b, add_y, sub_y, mul_y);

        a = 32'hbf000000; b = 32'hbe000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 115, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 116, a, b, add_y, sub_y, mul_y);

        a = 32'hc0900000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 117, a, b, add_y, sub_y, mul_y);

        a = 32'h3fc00000; b = 32'h41800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 118, a, b, add_y, sub_y, mul_y);

        a = 32'hc0000000; b = 32'h00000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 119, a, b, add_y, sub_y, mul_y);

        a = 32'h00000000; b = 32'hc1800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 120, a, b, add_y, sub_y, mul_y);

        a = 32'h40000000; b = 32'h00000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 121, a, b, add_y, sub_y, mul_y);

        a = 32'hc1800000; b = 32'hc0900000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 122, a, b, add_y, sub_y, mul_y);

        a = 32'h41000000; b = 32'h3f800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 123, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'hbe800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 124, a, b, add_y, sub_y, mul_y);

        a = 32'h40500000; b = 32'hbf800000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 125, a, b, add_y, sub_y, mul_y);

        a = 32'hbfc00000; b = 32'h3f000000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 126, a, b, add_y, sub_y, mul_y);

        a = 32'h3f800000; b = 32'h3fc00000; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", 127, a, b, add_y, sub_y, mul_y);

        $finish;
    end
endmodule
