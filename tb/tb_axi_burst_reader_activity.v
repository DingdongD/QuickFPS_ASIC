`timescale 1ns/1ps
module tb_axi_burst_reader_activity;
    localparam ADDR_W = 64;
    localparam DATA_W = 256;
    reg clk = 1'b0;
    always #0.5 clk = ~clk;
    reg rst_n = 1'b0;
    reg cmd_valid = 1'b0;
    wire cmd_ready, done, busy;
    wire arvalid;
    reg arready = 1'b1;
    wire [ADDR_W-1:0] araddr;
    wire [7:0] arlen;
    wire [2:0] arsize;
    wire [1:0] arburst;
    wire rvalid;
    wire rready;
    wire [DATA_W-1:0] rdata;
    wire rlast;
    wire out_valid;
    reg out_ready = 1'b1;
    wire [DATA_W-1:0] out_data;
    wire out_last;
    wire [31:0] bytes_completed;
    integer beats_left = 0;
    integer cycle = 0;
    integer burst_count = 0;
    reg [31:0] lfsr = 32'h1357_9bdf;
    reg ar_fire_q = 1'b0;
    reg r_fire_q = 1'b0;
    reg [7:0] arlen_q = 8'd0;
    reg [ADDR_W-1:0] araddr_q = {ADDR_W{1'b0}};

    assign rvalid = beats_left > 0;
    assign rlast = beats_left == 1;
    assign rdata = {8{lfsr}};

    // Keep the PTPX activity bench at the module defaults so the same source
    // instantiates the parameter-free mapped netlist after synthesis.
    axi_burst_reader dut (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .cmd_addr(64'h0000_0000_0000_0f00), .cmd_bytes(32'd1600),
        .done(done), .busy(busy),
        .m_axi_arvalid(arvalid), .m_axi_arready(arready),
        .m_axi_araddr(araddr), .m_axi_arlen(arlen),
        .m_axi_arsize(arsize), .m_axi_arburst(arburst),
        .m_axi_rvalid(rvalid), .m_axi_rready(rready), .m_axi_rdata(rdata),
        .m_axi_rlast(rlast), .m_axi_rresp(2'b00),
        .out_valid(out_valid), .out_ready(out_ready),
        .out_data(out_data), .out_last(out_last),
        .bytes_completed(bytes_completed)
    );

    always @(posedge clk) begin
        cycle <= cycle + 1;
        ar_fire_q <= arvalid && arready;
        r_fire_q <= rvalid && rready;
        if (arvalid && arready) begin
            arlen_q <= arlen;
            araddr_q <= araddr;
        end

        if (done) begin
            if (bytes_completed != 32'd1600)
                $fatal(1, "reader byte count mismatch");
            if (burst_count != 4)
                $fatal(1, "expected four read bursts, got %0d", burst_count);
            $display("AXI_READER_PASS cycles=%0d bursts=%0d", cycle, burst_count);
            $finish;
        end
    end

    always @(negedge clk) begin
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        out_ready <= (cycle % 7 != 0);

        if (ar_fire_q) begin
            if (beats_left != 0)
                $fatal(1, "overlapping read burst");
            beats_left <= arlen_q + 1;
            burst_count <= burst_count + 1;
            if ((araddr_q[11:0] + ((arlen_q + 1) * (DATA_W/8))) > 4096)
                $fatal(1, "read burst crossed a 4KB boundary");
        end else if (r_fire_q) begin
            beats_left <= beats_left - 1;
        end
    end

    initial begin
        $dumpfile("build/activity/axi_burst_reader.vcd");
        $dumpvars(0, tb_axi_burst_reader_activity.dut);
        repeat (5) @(negedge clk);
        rst_n <= 1'b1;
        @(negedge clk);
        cmd_valid <= 1'b1;
        @(negedge clk);
        cmd_valid <= 1'b0;
        repeat (2000) @(posedge clk);
        $fatal(1, "reader timeout");
    end
endmodule
