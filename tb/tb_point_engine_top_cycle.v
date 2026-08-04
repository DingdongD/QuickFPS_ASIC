`timescale 1ns/1ps
module tb_point_engine_top_cycle;
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
    reg [R*96-1:0] co_rdata = {R{96'h3f800000_3f000000_3e800000}};
    wire [PIDX_W-1:0] di_raddr;
    reg [R*32-1:0] di_rdata = {R{32'h7f800000}};
    wire [R-1:0] di_wstrb;
    wire [PIDX_W-1:0] di_waddr;
    wire [R*32-1:0] di_wdata;

    integer cycle_count = 0;
    integer accept_cycle = -1;

    point_engine_top #(
        .L(L), .R(R), .LIDX_W(11), .BIDX_W(BIDX_W),
        .PIDX_W(PIDX_W), .NUMP_W(NUMP_W), .ADDR_W(ADDR_W),
        .MCNT_W(MCNT_W), .BF_W(BF_W), .FP_W(FP_W)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .bkt_empty(bkt_empty), .bkt_rdata(bkt_rdata), .bkt_ren(bkt_ren),
        .fp_full(fp_full), .fp_wen(fp_wen), .fp_wdata(fp_wdata),
        .mb_bid(mb_bid), .mb_k(mb_k), .mb_rdata(mb_rdata),
        .co_addr(co_addr), .co_rdata(co_rdata),
        .di_raddr(di_raddr), .di_rdata(di_rdata),
        .di_wstrb(di_wstrb), .di_waddr(di_waddr), .di_wdata(di_wdata)
    );

    always @(posedge clk) begin
        cycle_count <= cycle_count + 1;
        if (bkt_ren && !bkt_empty) begin
            accept_cycle <= cycle_count;
            bkt_empty <= 1'b1;
            $display("PTOP_ACCEPT %0d", cycle_count);
        end
        if (fp_wen) begin
            $display("PTOP_PUSH %0d LATENCY %0d", cycle_count,
                     cycle_count - accept_cycle);
            if ((cycle_count - accept_cycle) != 38) begin
                $display("PTOP_CYCLE_FAIL expected=38 got=%0d",
                         cycle_count - accept_cycle);
                $fatal(1);
            end
            $display("PTOP_CYCLE_PASS");
            $finish;
        end
    end

    initial begin
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        bkt_rdata[0 +: BIDX_W] = 9'd2;
        bkt_rdata[BIDX_W +: ADDR_W] = 32'd0;
        bkt_rdata[BIDX_W+ADDR_W +: NUMP_W] = 16'd48;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W +: 32] = 32'h00000000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+32 +: 32] = 32'h00000000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+64 +: 32] = 32'h00000000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+96 +: MCNT_W] = 8'd3;
        bkt_empty <= 1'b0;

        repeat (128) @(posedge clk);
        $fatal(1, "PTOP timeout");
    end
endmodule
