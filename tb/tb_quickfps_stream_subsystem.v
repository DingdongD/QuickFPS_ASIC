`timescale 1ns/1ps
module tb_quickfps_stream_subsystem;
    localparam ADDR_W=64;
    localparam DATA_W=256;
    localparam COUNT_W=24;

    reg clk=1'b0;
    always #0.5 clk=~clk;
    reg rst_n=1'b0;
    reg bucket_valid=1'b0;
    wire bucket_ready, bucket_done, busy;

    wire coord_stream_valid;
    reg coord_stream_ready=1'b1;
    wire [DATA_W-1:0] coord_stream_data;
    wire coord_stream_last;
    wire dist_stream_valid;
    reg dist_stream_ready=1'b1;
    wire [DATA_W-1:0] dist_stream_data;
    wire dist_stream_last;
    reg write_stream_valid=1'b1;
    wire write_stream_ready;
    reg [DATA_W-1:0] write_stream_data={DATA_W{1'b0}};

    wire compute_start;
    reg compute_ready=1'b1;
    wire [COUNT_W-1:0] compute_point_count;
    wire [7:0] compute_merge_count;
    wire compute_slot;
    reg compute_done=1'b0;

    wire c_arvalid; reg c_arready=1'b1;
    wire [ADDR_W-1:0] c_araddr; wire [7:0] c_arlen;
    wire [2:0] c_arsize; wire [1:0] c_arburst;
    wire c_rvalid, c_rready, c_rlast; wire [DATA_W-1:0] c_rdata;
    wire d_arvalid; reg d_arready=1'b1;
    wire [ADDR_W-1:0] d_araddr; wire [7:0] d_arlen;
    wire [2:0] d_arsize; wire [1:0] d_arburst;
    wire d_rvalid, d_rready, d_rlast; wire [DATA_W-1:0] d_rdata;
    wire w_awvalid; reg w_awready=1'b1;
    wire [ADDR_W-1:0] w_awaddr; wire [7:0] w_awlen;
    wire [2:0] w_awsize; wire [1:0] w_awburst;
    wire w_wvalid; reg w_wready=1'b1;
    wire [DATA_W-1:0] w_wdata; wire [DATA_W/8-1:0] w_wstrb;
    wire w_wlast; reg w_bvalid=1'b0; wire w_bready;

    integer c_beats=0, d_beats=0;
    integer c_bursts=0, d_bursts=0, w_bursts=0;
    integer compute_count=0, compute_timer=-1;
    integer cycle=0;
    reg [31:0] lfsr=32'h7654_3211;

    assign c_rvalid = c_beats > 0;
    assign c_rlast = c_beats == 1;
    assign c_rdata = {8{lfsr}};
    assign d_rvalid = d_beats > 0;
    assign d_rlast = d_beats == 1;
    assign d_rdata = {8{lfsr ^ 32'ha5a5_5a5a}};

    quickfps_stream_subsystem #(
        .ADDR_W(ADDR_W), .AXI_DATA_W(DATA_W),
        .COUNT_W(COUNT_W), .CHUNK_POINTS(256)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .bucket_valid(bucket_valid), .bucket_ready(bucket_ready),
        .bucket_coord_addr(64'h0000_0000_0000_2000),
        .bucket_dist_addr(64'h0000_0000_1000_2000),
        .bucket_point_count(24'd300), .bucket_merge_count(8'd3),
        .bucket_done(bucket_done), .busy(busy),
        .coord_stream_valid(coord_stream_valid),
        .coord_stream_ready(coord_stream_ready),
        .coord_stream_data(coord_stream_data), .coord_stream_last(coord_stream_last),
        .dist_stream_valid(dist_stream_valid), .dist_stream_ready(dist_stream_ready),
        .dist_stream_data(dist_stream_data), .dist_stream_last(dist_stream_last),
        .write_stream_valid(write_stream_valid),
        .write_stream_ready(write_stream_ready),
        .write_stream_data(write_stream_data),
        .compute_start(compute_start), .compute_ready(compute_ready),
        .compute_point_count(compute_point_count),
        .compute_merge_count(compute_merge_count), .compute_slot(compute_slot),
        .compute_done(compute_done),
        .c_axi_arvalid(c_arvalid), .c_axi_arready(c_arready),
        .c_axi_araddr(c_araddr), .c_axi_arlen(c_arlen),
        .c_axi_arsize(c_arsize), .c_axi_arburst(c_arburst),
        .c_axi_rvalid(c_rvalid), .c_axi_rready(c_rready),
        .c_axi_rdata(c_rdata), .c_axi_rlast(c_rlast), .c_axi_rresp(2'b00),
        .d_axi_arvalid(d_arvalid), .d_axi_arready(d_arready),
        .d_axi_araddr(d_araddr), .d_axi_arlen(d_arlen),
        .d_axi_arsize(d_arsize), .d_axi_arburst(d_arburst),
        .d_axi_rvalid(d_rvalid), .d_axi_rready(d_rready),
        .d_axi_rdata(d_rdata), .d_axi_rlast(d_rlast), .d_axi_rresp(2'b00),
        .w_axi_awvalid(w_awvalid), .w_axi_awready(w_awready),
        .w_axi_awaddr(w_awaddr), .w_axi_awlen(w_awlen),
        .w_axi_awsize(w_awsize), .w_axi_awburst(w_awburst),
        .w_axi_wvalid(w_wvalid), .w_axi_wready(w_wready),
        .w_axi_wdata(w_wdata), .w_axi_wstrb(w_wstrb), .w_axi_wlast(w_wlast),
        .w_axi_bvalid(w_bvalid), .w_axi_bready(w_bready), .w_axi_bresp(2'b00)
    );

    always @(posedge clk) begin
        cycle <= cycle + 1;
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        write_stream_data <= {8{lfsr ^ 32'h0f0f_f0f0}};
        coord_stream_ready <= (cycle % 11 != 0);
        dist_stream_ready <= (cycle % 13 != 0);
        w_wready <= (cycle % 7 != 0);
        compute_done <= 1'b0;

        if (c_arvalid && c_arready) begin
            if (c_beats != 0) $fatal(1, "coordinate AXI overlap");
            c_beats <= c_arlen + 1;
            c_bursts <= c_bursts + 1;
        end else if (c_rvalid && c_rready) c_beats <= c_beats - 1;

        if (d_arvalid && d_arready) begin
            if (d_beats != 0) $fatal(1, "distance AXI overlap");
            d_beats <= d_arlen + 1;
            d_bursts <= d_bursts + 1;
        end else if (d_rvalid && d_rready) d_beats <= d_beats - 1;

        if (w_awvalid && w_awready) w_bursts <= w_bursts + 1;
        if (w_wvalid && w_wready && w_wlast) w_bvalid <= 1'b1;
        if (w_bvalid && w_bready) w_bvalid <= 1'b0;

        if (compute_start && compute_ready) begin
            if (compute_timer >= 0) $fatal(1, "compute overlap");
            compute_timer <= 12;
            compute_count <= compute_count + 1;
            if (compute_merge_count != 8'd3) $fatal(1, "merge count mismatch");
        end else if (compute_timer == 0) begin
            compute_done <= 1'b1;
            compute_timer <= -1;
        end else if (compute_timer > 0) compute_timer <= compute_timer - 1;

        if (bucket_done) begin
            if (compute_count != 2)
                $fatal(1, "expected two compute chunks, got %0d", compute_count);
            if (c_bursts == 0 || d_bursts == 0 || w_bursts == 0)
                $fatal(1, "missing AXI traffic");
            $display("STREAM_SUBSYSTEM_PASS cycles=%0d c=%0d d=%0d w=%0d",
                     cycle, c_bursts, d_bursts, w_bursts);
            $finish;
        end
    end

    initial begin
        $dumpfile("build/activity/quickfps_stream_subsystem.vcd");
        $dumpvars(0, tb_quickfps_stream_subsystem.dut);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        bucket_valid <= 1'b1;
        @(posedge clk);
        bucket_valid <= 1'b0;
        repeat (10000) @(posedge clk);
        $fatal(1, "stream subsystem timeout");
    end
endmodule
