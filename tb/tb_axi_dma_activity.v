`timescale 1ns/1ps
module tb_axi_dma_activity;
    localparam ADDR_W = 64;
    localparam DATA_W = 256;

    reg clk = 1'b0;
    always #0.5 clk = ~clk;  // 1 GHz
    reg rst_n = 1'b0;
    integer cycle = 0;
    reg [31:0] lfsr = 32'h1ace_beef;

    reg rd_cmd_valid = 1'b0;
    wire rd_cmd_ready;
    wire rd_done, rd_busy;
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
    wire [31:0] rd_bytes;
    integer rd_beats_left = 0;
    reg rd_complete_seen = 1'b0;

    reg wr_cmd_valid = 1'b0;
    wire wr_cmd_ready;
    wire wr_done, wr_busy;
    reg in_valid = 1'b1;
    wire in_ready;
    wire [DATA_W-1:0] in_data;
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
    wire [31:0] wr_bytes;
    reg wr_complete_seen = 1'b0;

    assign rvalid = rd_beats_left > 0;
    assign rlast = rd_beats_left == 1;
    assign rdata = {8{lfsr}};
    assign in_data = {8{lfsr ^ 32'h55aa_33cc}};

    axi_burst_reader #(
        .ADDR_W(ADDR_W), .DATA_W(DATA_W), .MAX_BURST_BEATS(16)
    ) u_reader (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(rd_cmd_valid), .cmd_ready(rd_cmd_ready),
        .cmd_addr(64'h0000_0000_0000_0f00), .cmd_bytes(32'd1600),
        .done(rd_done), .busy(rd_busy),
        .m_axi_arvalid(arvalid), .m_axi_arready(arready),
        .m_axi_araddr(araddr), .m_axi_arlen(arlen),
        .m_axi_arsize(arsize), .m_axi_arburst(arburst),
        .m_axi_rvalid(rvalid), .m_axi_rready(rready), .m_axi_rdata(rdata),
        .m_axi_rlast(rlast), .m_axi_rresp(2'b00),
        .out_valid(out_valid), .out_ready(out_ready),
        .out_data(out_data), .out_last(out_last),
        .bytes_completed(rd_bytes)
    );

    axi_burst_writer #(
        .ADDR_W(ADDR_W), .DATA_W(DATA_W), .MAX_BURST_BEATS(16)
    ) u_writer (
        .clk(clk), .rst_n(rst_n),
        .cmd_valid(wr_cmd_valid), .cmd_ready(wr_cmd_ready),
        .cmd_addr(64'h0000_0000_1000_0f80), .cmd_bytes(32'd1000),
        .done(wr_done), .busy(wr_busy),
        .in_valid(in_valid), .in_ready(in_ready), .in_data(in_data),
        .m_axi_awvalid(awvalid), .m_axi_awready(awready),
        .m_axi_awaddr(awaddr), .m_axi_awlen(awlen),
        .m_axi_awsize(awsize), .m_axi_awburst(awburst),
        .m_axi_wvalid(wvalid), .m_axi_wready(wready),
        .m_axi_wdata(wdata), .m_axi_wstrb(wstrb), .m_axi_wlast(wlast),
        .m_axi_bvalid(bvalid), .m_axi_bready(bready), .m_axi_bresp(2'b00),
        .bytes_completed(wr_bytes)
    );

    always @(posedge clk) begin
        cycle <= cycle + 1;
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        out_ready <= (cycle % 7 != 0);
        wready <= (cycle % 5 != 0);

        if (arvalid && arready) begin
            if (rd_beats_left != 0)
                $fatal(1, "reader issued overlapping burst");
            rd_beats_left <= arlen + 1;
        end else if (rvalid && rready) begin
            rd_beats_left <= rd_beats_left - 1;
        end

        if (wvalid && wready && wlast)
            bvalid <= 1'b1;
        if (bvalid && bready)
            bvalid <= 1'b0;

        if (rd_done)
            rd_complete_seen <= 1'b1;
        if (wr_done)
            wr_complete_seen <= 1'b1;

        if ((rd_complete_seen || rd_done) &&
            (wr_complete_seen || wr_done)) begin
            if (rd_bytes != 32'd1600 || wr_bytes != 32'd1000)
                $fatal(1, "DMA byte counter mismatch");
            $display("AXI_DMA_PASS cycles=%0d", cycle);
            $finish;
        end
    end

    initial begin
        $dumpfile("build/activity/axi_dma_activity.vcd");
        $dumpvars(0, tb_axi_dma_activity);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        rd_cmd_valid <= 1'b1;
        wr_cmd_valid <= 1'b1;
        @(posedge clk);
        rd_cmd_valid <= 1'b0;
        wr_cmd_valid <= 1'b0;
        repeat (2000) @(posedge clk);
        $fatal(1, "AXI DMA timeout");
    end
endmodule
