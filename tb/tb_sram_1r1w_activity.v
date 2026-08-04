`timescale 1ns/1ps
module tb_sram_1r1w_activity;
    localparam WIDTH = 128;
    localparam AW = 8;
    reg clk = 1'b0;
    always #0.5 clk = ~clk;
    reg rst_n = 1'b0;
    reg rd_valid = 1'b0;
    wire rd_ready;
    reg [AW-1:0] rd_addr = 0;
    wire rsp_valid;
    wire [WIDTH-1:0] rsp_data;
    reg wr_valid = 1'b0;
    wire wr_ready;
    reg [AW-1:0] wr_addr = 0;
    reg [WIDTH-1:0] wr_data = 0;
    reg [WIDTH/8-1:0] wr_strb = {WIDTH/8{1'b1}};
    integer cycle = 0;
    integer responses = 0;
    reg [31:0] lfsr = 32'hdead_beef;

    sram_1r1w_ptpx dut (
        .clk(clk), .rst_n(rst_n),
        .rd_valid(rd_valid), .rd_ready(rd_ready), .rd_addr(rd_addr),
        .rsp_valid(rsp_valid), .rsp_data(rsp_data),
        .wr_valid(wr_valid), .wr_ready(wr_ready), .wr_addr(wr_addr),
        .wr_data(wr_data), .wr_strb(wr_strb)
    );

    always @(posedge clk) begin
        cycle <= cycle + 1;
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        if (rst_n) begin
            wr_valid <= (cycle < 300) && (cycle % 3 != 0);
            wr_addr <= wr_addr + 1'b1;
            wr_data <= {4{lfsr}};
            wr_strb <= (cycle % 5 == 0) ? 16'h0f0f : 16'hffff;
            rd_valid <= (cycle > 20) && (cycle < 340) && (cycle % 4 != 0);
            rd_addr <= rd_addr + 3;
        end
        if (rsp_valid)
            responses <= responses + 1;
        if (cycle == 400) begin
            if (responses == 0) $fatal(1, "no SRAM responses observed");
            $display("SRAM_ACTIVITY_PASS responses=%0d", responses);
            $finish;
        end
    end

    initial begin
        $dumpfile("build/activity/sram_1r1w_sync.vcd");
        $dumpvars(0, tb_sram_1r1w_activity.dut);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        repeat (500) @(posedge clk);
        $fatal(1, "SRAM activity timeout");
    end
endmodule
