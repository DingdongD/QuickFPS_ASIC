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
    localparam NUM_POINTS = 48;
    localparam MERGE_COUNT = 3;
    localparam PASSES = (MERGE_COUNT + 1 + L - 1) / L;
    localparam POINT_IO_PIPELINE_CYCLES = 1;
    localparam EXPECTED_LATENCY =
        PASSES * ((NUM_POINTS / R) + (6 * L)) + 2 +
        POINT_IO_PIPELINE_CYCLES;

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
    reg [R*32-1:0] di_rdata = {R{32'h7f800000}};
    wire [R-1:0] di_wstrb;
    wire [PIDX_W-1:0] di_waddr;
    wire [R*32-1:0] di_wdata;

    integer cycle_count = 0;
    integer accept_cycle = -1;
    integer lane;

    function [31:0] fp_x;
        input [3:0] value;
        begin
            case (value)
                4'd0:  fp_x = 32'h00000000;
                4'd1:  fp_x = 32'h3f800000;
                4'd2:  fp_x = 32'h40000000;
                4'd3:  fp_x = 32'h40400000;
                4'd4:  fp_x = 32'h40800000;
                4'd5:  fp_x = 32'h40a00000;
                4'd6:  fp_x = 32'h40c00000;
                4'd7:  fp_x = 32'h40e00000;
                4'd8:  fp_x = 32'h41000000;
                4'd9:  fp_x = 32'h41100000;
                4'd10: fp_x = 32'h41200000;
                4'd11: fp_x = 32'h41300000;
                4'd12: fp_x = 32'h41400000;
                4'd13: fp_x = 32'h41500000;
                4'd14: fp_x = 32'h41600000;
                default: fp_x = 32'h41700000;
            endcase
        end
    endfunction

    always @* begin
        co_rdata = {R*96{1'b0}};
        for (lane = 0; lane < R; lane = lane + 1)
            co_rdata[lane*96 +: 32] = fp_x(co_addr[3:0] + lane[3:0]);
    end

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
            if ((cycle_count - accept_cycle) != EXPECTED_LATENCY) begin
                $display("PTOP_CYCLE_FAIL expected=%0d got=%0d",
                         EXPECTED_LATENCY,
                         cycle_count - accept_cycle);
                $fatal(1);
            end
            if (fp_wdata[0 +: 96] !== 96'h00000000_00000000_41700000 ||
                fp_wdata[96 +: 32] !== 32'h43610000 ||
                fp_wdata[128 +: PIDX_W] !== 18'd15 ||
                fp_wdata[128+PIDX_W +: BIDX_W] !== 9'd2) begin
                $display("PTOP_DATA_FAIL data=%h", fp_wdata);
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
        bkt_rdata[BIDX_W+ADDR_W +: NUMP_W] = NUM_POINTS[NUMP_W-1:0];
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W +: 32] = 32'h00000000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+32 +: 32] = 32'h00000000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+64 +: 32] = 32'h00000000;
        bkt_rdata[BIDX_W+ADDR_W+NUMP_W+96 +: MCNT_W] =
            MERGE_COUNT[MCNT_W-1:0];
        bkt_empty <= 1'b0;

        repeat (128) @(posedge clk);
        $fatal(1, "PTOP timeout");
    end
endmodule
