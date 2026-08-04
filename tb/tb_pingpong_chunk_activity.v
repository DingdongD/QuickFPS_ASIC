`timescale 1ns/1ps
module tb_pingpong_chunk_activity;
    localparam ADDR_W = 64;
    localparam COUNT_W = 16;
    localparam MCNT_W = 8;
    reg clk = 1'b0;
    always #0.5 clk = ~clk;
    reg rst_n = 1'b0;
    reg bucket_valid = 1'b0;
    wire bucket_ready, bucket_done, busy;
    wire coord_cmd_valid;
    reg coord_cmd_ready = 1'b1;
    wire [ADDR_W-1:0] coord_cmd_addr;
    wire [COUNT_W+4-1:0] coord_cmd_bytes;
    reg coord_done = 1'b0;
    wire dist_rd_cmd_valid;
    reg dist_rd_cmd_ready = 1'b1;
    wire [ADDR_W-1:0] dist_rd_cmd_addr;
    wire [COUNT_W+2-1:0] dist_rd_cmd_bytes;
    reg dist_rd_done = 1'b0;
    wire dist_wr_cmd_valid;
    reg dist_wr_cmd_ready = 1'b1;
    wire [ADDR_W-1:0] dist_wr_cmd_addr;
    wire [COUNT_W+2-1:0] dist_wr_cmd_bytes;
    reg dist_wr_done = 1'b0;
    wire compute_start;
    reg compute_ready = 1'b1;
    wire [COUNT_W-1:0] compute_point_count;
    wire [MCNT_W-1:0] compute_merge_count;
    wire compute_slot;
    reg compute_done = 1'b0;
    integer coord_timer=-1, dist_timer=-1, write_timer=-1, compute_timer=-1;
    integer cycle=0;

    pingpong_chunk_ctrl #(
        .ADDR_W(ADDR_W), .COUNT_W(COUNT_W), .MCNT_W(MCNT_W),
        .CHUNK_POINTS(256), .COORD_BYTES(12), .DIST_BYTES(4)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .bucket_valid(bucket_valid), .bucket_ready(bucket_ready),
        .bucket_point_ptr(64'd4096), .bucket_point_count(16'd1200),
        .bucket_merge_count(8'd9), .bucket_done(bucket_done), .busy(busy),
        .coord_cmd_valid(coord_cmd_valid), .coord_cmd_ready(coord_cmd_ready),
        .coord_cmd_addr(coord_cmd_addr), .coord_cmd_bytes(coord_cmd_bytes),
        .coord_done(coord_done),
        .dist_rd_cmd_valid(dist_rd_cmd_valid), .dist_rd_cmd_ready(dist_rd_cmd_ready),
        .dist_rd_cmd_addr(dist_rd_cmd_addr), .dist_rd_cmd_bytes(dist_rd_cmd_bytes),
        .dist_rd_done(dist_rd_done),
        .dist_wr_cmd_valid(dist_wr_cmd_valid), .dist_wr_cmd_ready(dist_wr_cmd_ready),
        .dist_wr_cmd_addr(dist_wr_cmd_addr), .dist_wr_cmd_bytes(dist_wr_cmd_bytes),
        .dist_wr_done(dist_wr_done),
        .compute_start(compute_start), .compute_ready(compute_ready),
        .compute_point_count(compute_point_count),
        .compute_merge_count(compute_merge_count), .compute_slot(compute_slot),
        .compute_done(compute_done)
    );

    always @(posedge clk) begin
        cycle <= cycle + 1;
        coord_done <= 1'b0;
        dist_rd_done <= 1'b0;
        dist_wr_done <= 1'b0;
        compute_done <= 1'b0;
        coord_cmd_ready <= (cycle % 11 != 0);
        dist_rd_cmd_ready <= (cycle % 13 != 0);
        dist_wr_cmd_ready <= (cycle % 7 != 0);
        compute_ready <= (cycle % 17 != 0);

        if (coord_cmd_valid && coord_cmd_ready) coord_timer <= 18;
        else if (coord_timer == 0) begin coord_done <= 1'b1; coord_timer <= -1; end
        else if (coord_timer > 0) coord_timer <= coord_timer - 1;

        if (dist_rd_cmd_valid && dist_rd_cmd_ready) dist_timer <= 14;
        else if (dist_timer == 0) begin dist_rd_done <= 1'b1; dist_timer <= -1; end
        else if (dist_timer > 0) dist_timer <= dist_timer - 1;

        if (compute_start && compute_ready)
            compute_timer <= 30 + compute_point_count / 4;
        else if (compute_timer == 0) begin compute_done <= 1'b1; compute_timer <= -1; end
        else if (compute_timer > 0) compute_timer <= compute_timer - 1;

        if (dist_wr_cmd_valid && dist_wr_cmd_ready) write_timer <= 12;
        else if (write_timer == 0) begin dist_wr_done <= 1'b1; write_timer <= -1; end
        else if (write_timer > 0) write_timer <= write_timer - 1;

        if (bucket_done) begin
            $display("PINGPONG_ACTIVITY_PASS cycles=%0d", cycle);
            $finish;
        end
    end

    initial begin
        $dumpfile("build/activity/pingpong_chunk_ctrl.vcd");
        $dumpvars(0, tb_pingpong_chunk_activity.dut);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        bucket_valid <= 1'b1;
        @(posedge clk);
        bucket_valid <= 1'b0;
        repeat (10000) @(posedge clk);
        $fatal(1, "pingpong activity timeout");
    end
endmodule
