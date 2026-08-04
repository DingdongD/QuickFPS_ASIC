`timescale 1ns/1ps
module tb_quickfps_core_end2end;
    localparam BIDX_W = 9;
    localparam PIDX_W = 18;
    localparam NUMP_W = 16;
    localparam ADDR_W = 32;
    localparam MCNT_W = 8;
    localparam ENTRY_W = 368 + PIDX_W + MCNT_W;
    localparam RESULT_W = 96 + PIDX_W;

    localparam E_MINX=0, E_MINY=32, E_MINZ=64;
    localparam E_MAXX=96, E_MAXY=128, E_MAXZ=160;
    localparam E_PTR=192, E_NUMP=224;
    localparam E_FX=240, E_FY=272, E_FZ=304;
    localparam E_FDIST=336, E_FIDX=368, E_MCNT=E_FIDX+PIDX_W;

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;
    reg start = 1'b0;
    wire busy, done;

    reg [PIDX_W-1:0] sample_n = 18'd4;
    reg [BIDX_W-1:0] bucket_m = 9'd1;
    reg [31:0] p0x = 32'h0000_0000;
    reg [31:0] p0y = 32'h0000_0000;
    reg [31:0] p0z = 32'h0000_0000;
    reg [PIDX_W-1:0] p0idx = 18'd0;

    reg host_bb_wen = 1'b0;
    reg [BIDX_W-1:0] host_bb_waddr = 0;
    reg [ENTRY_W-1:0] host_bb_wdata = 0;
    reg host_coord_wen = 1'b0;
    reg [PIDX_W-1:0] host_coord_waddr = 0;
    reg [95:0] host_coord_wdata = 0;
    reg host_dist_wen = 1'b0;
    reg [PIDX_W-1:0] host_dist_waddr = 0;
    reg [31:0] host_dist_wdata = 0;
    reg [PIDX_W-1:0] result_raddr = 0;
    wire [RESULT_W-1:0] result_rdata;

    quickfps_core_top #(
        .BIDX_W(BIDX_W), .PIDX_W(PIDX_W),
        .NUMP_W(NUMP_W), .ADDR_W(ADDR_W), .MCNT_W(MCNT_W),
        .MB_CAP(8), .FIFO_DEPTH(4),
        .BUCKETS(2), .POINT_DEPTH(16),
        .ENTRY_W(ENTRY_W), .RESULT_W(RESULT_W)
    ) dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .busy(busy), .done(done),
        .sample_n(sample_n), .bucket_m(bucket_m),
        .p0x(p0x), .p0y(p0y), .p0z(p0z), .p0idx(p0idx),
        .host_bb_wen(host_bb_wen),
        .host_bb_waddr(host_bb_waddr), .host_bb_wdata(host_bb_wdata),
        .host_coord_wen(host_coord_wen),
        .host_coord_waddr(host_coord_waddr),
        .host_coord_wdata(host_coord_wdata),
        .host_dist_wen(host_dist_wen),
        .host_dist_waddr(host_dist_waddr),
        .host_dist_wdata(host_dist_wdata),
        .result_raddr(result_raddr), .result_rdata(result_rdata)
    );

    function [31:0] f32_x;
        input integer x;
        begin
            case (x)
                0: f32_x = 32'h0000_0000;
                1: f32_x = 32'h3f80_0000;
                2: f32_x = 32'h4000_0000;
                3: f32_x = 32'h4040_0000;
                4: f32_x = 32'h4080_0000;
                5: f32_x = 32'h40a0_0000;
                6: f32_x = 32'h40c0_0000;
                7: f32_x = 32'h40e0_0000;
                default: f32_x = 32'h0000_0000;
            endcase
        end
    endfunction

    task write_point;
        input [PIDX_W-1:0] addr;
        input [31:0] x;
        begin
            host_coord_wen <= 1'b1;
            host_coord_waddr <= addr;
            host_coord_wdata <= {32'h0, 32'h0, x};
            host_dist_wen <= 1'b1;
            host_dist_waddr <= addr;
            host_dist_wdata <= 32'h7f80_0000;
            @(posedge clk);
            host_coord_wen <= 1'b0;
            host_dist_wen <= 1'b0;
        end
    endtask

    task write_bucket;
        input [BIDX_W-1:0] bid;
        input [31:0] minx;
        input [31:0] maxx;
        input [ADDR_W-1:0] ptr;
        input [NUMP_W-1:0] nump;
        reg [ENTRY_W-1:0] e;
        begin
            e = {ENTRY_W{1'b0}};
            e[E_MINX +: 32] = minx;
            e[E_MINY +: 32] = 32'h0;
            e[E_MINZ +: 32] = 32'h0;
            e[E_MAXX +: 32] = maxx;
            e[E_MAXY +: 32] = 32'h0;
            e[E_MAXZ +: 32] = 32'h0;
            e[E_PTR +: ADDR_W] = ptr;
            e[E_NUMP +: NUMP_W] = nump;
            e[E_FX +: 32] = 32'h0;
            e[E_FY +: 32] = 32'h0;
            e[E_FZ +: 32] = 32'h0;
            e[E_FDIST +: 32] = 32'h0;
            e[E_FIDX +: PIDX_W] = ptr[PIDX_W-1:0];
            e[E_MCNT +: MCNT_W] = {MCNT_W{1'b0}};
            host_bb_wen <= 1'b1;
            host_bb_waddr <= bid;
            host_bb_wdata <= e;
            @(posedge clk);
            host_bb_wen <= 1'b0;
        end
    endtask

    task check_result;
        input [PIDX_W-1:0] pos;
        input [PIDX_W-1:0] expected_idx;
        begin
            result_raddr = pos;
            #1;
            if (result_rdata[96 +: PIDX_W] !== expected_idx) begin
                $display("CORE_E2E_FAIL pos=%0d got=%0d expected=%0d raw=%h",
                         pos, result_rdata[96 +: PIDX_W],
                         expected_idx, result_rdata);
                $fatal(1);
            end
        end
    endtask

    integer i;
    initial begin
        repeat (4) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        for (i = 0; i < 8; i = i + 1)
            write_point(i[PIDX_W-1:0], f32_x(i));

        write_bucket(9'd0, f32_x(0), f32_x(3), 32'd0, 16'd4);
        write_bucket(9'd1, f32_x(4), f32_x(7), 32'd4, 16'd4);

        start <= 1'b1;
        @(posedge clk);
        start <= 1'b0;

        fork
            begin
                wait(done);
                @(posedge clk);
                check_result(18'd0, 18'd0);
                check_result(18'd1, 18'd7);
                check_result(18'd2, 18'd3);
                check_result(18'd3, 18'd5);
                $display("CORE_E2E_PASS sequence=0,7,3,5");
                $finish;
            end
            begin
                repeat (5000) @(posedge clk);
                $fatal(1, "CORE_E2E_TIMEOUT");
            end
        join
    end
endmodule
