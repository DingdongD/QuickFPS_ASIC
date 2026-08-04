`timescale 1ns/1ps
module tb_axi_burst_writer_activity;
    localparam ADDR_W = 64;
    localparam DATA_W = 256;
    reg clk = 1'b0;
    always #0.5 clk = ~clk;
    reg rst_n = 1'b0;
    reg cmd_valid = 1'b0;
    wire cmd_ready, done, busy;
    reg in_valid = 1'b1;
    wire in_ready;
    reg [DATA_W-1:0] in_data = {DATA_W{1'b0}};
    wire awvalid;
    reg awready = 1'b1;
    wire [ADDR_W-1:0] awaddr;
    wire [7:0] awlen;
    wire [2:0] awsize;
    wire [1:0] awburst;
    wire wvalid;
    reg wready = 1'b1;
    wire [DATA_W-1:0] wdata;
    wire [DATA_W/8-1:0] wstrb;
    wire wlast;
    reg bvalid = 1'b0;
    wire bready;
    wire [31:0] bytes_completed;
    integer cycle = 0;
    reg [31:0] lfsr = 32'h2468_ace1;

    axi_burst_writer dut (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .cmd_addr(64'h0000_0000_1000_0f80), .cmd_bytes(32'd1000),
        .done(done), .busy(busy),
        .in_valid(in_valid), .in_ready(in_ready), .in_data(in_data),
        .m_axi_awvalid(awvalid), .m_axi_awready(awready),
        .m_axi_awaddr(awaddr), .m_axi_awlen(awlen),
        .m_axi_awsize(awsize), .m_axi_awburst(awburst),
        .m_axi_wvalid(wvalid), .m_axi_wready(wready),
        .m_axi_wdata(wdata), .m_axi_wstrb(wstrb), .m_axi_wlast(wlast),
        .m_axi_bvalid(bvalid), .m_axi_bready(bready), .m_axi_bresp(2'b00),
        .bytes_completed(bytes_completed)
    );

    always @(posedge clk) begin
        cycle <= cycle + 1;
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        in_data <= {8{lfsr}};
        wready <= (cycle % 5 != 0);
        if (wvalid && wready && wlast)
            bvalid <= 1'b1;
        if (bvalid && bready)
            bvalid <= 1'b0;
        if (done) begin
            if (bytes_completed != 32'd1000)
                $fatal(1, "writer byte count mismatch");
            $display("AXI_WRITER_PASS cycles=%0d", cycle);
            $finish;
        end
    end

    initial begin
        $dumpfile("build/activity/axi_burst_writer.vcd");
        $dumpvars(0, tb_axi_burst_writer_activity.dut);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        cmd_valid <= 1'b1;
        @(posedge clk);
        cmd_valid <= 1'b0;
        repeat (2000) @(posedge clk);
        $fatal(1, "writer timeout");
    end
endmodule
