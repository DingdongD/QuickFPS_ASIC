`timescale 1ns/1ps
module tb_point_engine_top_tail;
    localparam L = 4;
    localparam R = 4;
    localparam BIDX_W = 9;
    localparam PIDX_W = 18;
    localparam NUMP_W = 16;
    localparam ADDR_W = 32;
    localparam MCNT_W = 8;
    localparam BF_W = BIDX_W + ADDR_W + NUMP_W + 96 + MCNT_W;
    localparam FP_W = BIDX_W + 96 + 32 + PIDX_W;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg bkt_empty = 1'b1;
    reg [BF_W-1:0] bkt_rdata = {BF_W{1'b0}};
    wire bkt_ren;
    reg fp_full = 1'b0;
    wire fp_wen;
    wire [FP_W-1:0] fp_wdata;

    wire [BIDX_W-1:0] mb_bid;
    wire [7:0] mb_k;
    reg [95:0] mb_rdata = 96'h0;

    wire [PIDX_W-1:0] co_addr;
    reg [R*96-1:0] co_rdata;
    wire [PIDX_W-1:0] di_raddr;
    wire [R*32-1:0] di_rdata = {R{32'h7f80_0000}};
    wire [R-1:0] di_wstrb;
    wire [PIDX_W-1:0] di_waddr;
    wire [R*32-1:0] di_wdata;

    wire [31:0] out_x = fp_wdata[0 +: 32];
    wire [31:0] out_dist = fp_wdata[96 +: 32];
    wire [PIDX_W-1:0] out_idx = fp_wdata[128 +: PIDX_W];

    point_engine_top #(
        .L(L), .R(R), .LIDX_W(11),
        .BIDX_W(BIDX_W), .PIDX_W(PIDX_W),
        .NUMP_W(NUMP_W), .ADDR_W(ADDR_W), .MCNT_W(MCNT_W),
        .BF_W(BF_W), .FP_W(FP_W)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .bkt_empty(bkt_empty), .bkt_rdata(bkt_rdata), .bkt_ren(bkt_ren),
        .fp_full(fp_full), .fp_wen(fp_wen), .fp_wdata(fp_wdata),
        .mb_bid(mb_bid), .mb_k(mb_k), .mb_rdata(mb_rdata),
        .co_addr(co_addr), .co_rdata(co_rdata),
        .di_raddr(di_raddr), .di_rdata(di_rdata),
        .di_wstrb(di_wstrb), .di_waddr(di_waddr), .di_wdata(di_wdata)
    );

    // Combinational four-point-wide coordinate memory.  Five points force a
    // partial final batch: x={0,1,2,3,4}, y=z=0.
    always @* begin
        co_rdata = {R*96{1'b0}};
        case (co_addr)
            18'd0: begin
                co_rdata[0*96 +: 32] = 32'h0000_0000;
                co_rdata[1*96 +: 32] = 32'h3f80_0000;
                co_rdata[2*96 +: 32] = 32'h4000_0000;
                co_rdata[3*96 +: 32] = 32'h4040_0000;
            end
            18'd4: begin
                co_rdata[0*96 +: 32] = 32'h4080_0000;
            end
            default: co_rdata = {R*96{1'b0}};
        endcase
    end

    always @(posedge clk) begin
        if (bkt_ren && !bkt_empty)
            bkt_empty <= 1'b1;

        if (fp_wen) begin
            if (out_idx !== 18'd4 ||
                out_dist !== 32'h4180_0000 ||
                out_x !== 32'h4080_0000) begin
                $display("POINT_TOP_TAIL_FAIL idx=%0d dist=%08x x=%08x",
                         out_idx, out_dist, out_x);
                $fatal(1);
            end
            $display("POINT_TOP_TAIL_PASS");
            $finish;
        end
    end

    initial begin
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        bkt_rdata[0 +: BIDX_W] = 9'd2;
        bkt_rdata[BIDX_W +: ADDR_W] = 32'd0;
        bkt_rdata[BIDX_W+ADDR_W +: NUMP_W] = 16'd5;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W +: 32] = 32'h0000_0000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+32 +: 32] = 32'h0000_0000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+64 +: 32] = 32'h0000_0000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+96 +: MCNT_W] = 8'd0;
        bkt_empty <= 1'b0;

        repeat (300) @(posedge clk);
        $fatal(1, "POINT_TOP_TAIL_TIMEOUT");
    end
endmodule
