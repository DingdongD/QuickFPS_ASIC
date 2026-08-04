`timescale 1ns/1ps
module tb_pingpong_chunk_ctrl;
    localparam ADDR_W = 64;
    localparam COUNT_W = 16;
    localparam MCNT_W = 8;

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;

    reg bucket_valid = 1'b0;
    wire bucket_ready;
    reg [ADDR_W-1:0] bucket_coord_addr = 64'h0000_0000_0000_1000;
    reg [ADDR_W-1:0] bucket_dist_addr = 64'h0000_0000_1000_1000;
    reg [COUNT_W-1:0] bucket_point_count = 16'd600;
    reg [MCNT_W-1:0] bucket_merge_count = 8'd5;
    wire bucket_done;
    wire busy;

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

    integer coord_timer = -1;
    integer dist_timer = -1;
    integer write_timer = -1;
    integer compute_timer = -1;
    integer coord_count = 0;
    integer dist_count = 0;
    integer write_count = 0;
    integer compute_count = 0;
    integer cycle = 0;

    pingpong_chunk_ctrl #(
        .ADDR_W(ADDR_W), .COUNT_W(COUNT_W), .MCNT_W(MCNT_W),
        .CHUNK_POINTS(256), .COORD_BYTES(12), .DIST_BYTES(4)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .bucket_valid(bucket_valid), .bucket_ready(bucket_ready),
        .bucket_coord_addr(bucket_coord_addr),
        .bucket_dist_addr(bucket_dist_addr),
        .bucket_point_count(bucket_point_count),
        .bucket_merge_count(bucket_merge_count),
        .bucket_done(bucket_done), .busy(busy),
        .coord_cmd_valid(coord_cmd_valid), .coord_cmd_ready(coord_cmd_ready),
        .coord_cmd_addr(coord_cmd_addr), .coord_cmd_bytes(coord_cmd_bytes),
        .coord_done(coord_done),
        .dist_rd_cmd_valid(dist_rd_cmd_valid),
        .dist_rd_cmd_ready(dist_rd_cmd_ready),
        .dist_rd_cmd_addr(dist_rd_cmd_addr),
        .dist_rd_cmd_bytes(dist_rd_cmd_bytes), .dist_rd_done(dist_rd_done),
        .dist_wr_cmd_valid(dist_wr_cmd_valid),
        .dist_wr_cmd_ready(dist_wr_cmd_ready),
        .dist_wr_cmd_addr(dist_wr_cmd_addr),
        .dist_wr_cmd_bytes(dist_wr_cmd_bytes), .dist_wr_done(dist_wr_done),
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

        if (coord_cmd_valid && coord_cmd_ready) begin
            if (coord_timer >= 0) $fatal(1, "overlapping coord command");
            coord_timer <= 5;
            coord_count <= coord_count + 1;
            $display("QTRACE cycle=%0d component=pingpong event=coord_cmd chunk=%0d addr=%0d bytes=%0d",
                     cycle, coord_count, coord_cmd_addr, coord_cmd_bytes);
            if (coord_cmd_addr < bucket_coord_addr)
                $fatal(1, "coordinate address escaped coordinate region");
        end else if (coord_timer == 0) begin
            coord_done <= 1'b1;
            coord_timer <= -1;
            $display("QTRACE cycle=%0d component=pingpong event=coord_done chunk=%0d",
                     cycle, coord_count-1);
        end else if (coord_timer > 0) begin
            coord_timer <= coord_timer - 1;
        end

        if (dist_rd_cmd_valid && dist_rd_cmd_ready) begin
            if (dist_timer >= 0) $fatal(1, "overlapping dist-read command");
            dist_timer <= 7;
            dist_count <= dist_count + 1;
            $display("QTRACE cycle=%0d component=pingpong event=dist_read_cmd chunk=%0d addr=%0d bytes=%0d",
                     cycle, dist_count, dist_rd_cmd_addr, dist_rd_cmd_bytes);
            if (dist_rd_cmd_addr < bucket_dist_addr)
                $fatal(1, "MDT read address escaped distance region");
        end else if (dist_timer == 0) begin
            dist_rd_done <= 1'b1;
            dist_timer <= -1;
            $display("QTRACE cycle=%0d component=pingpong event=dist_read_done chunk=%0d",
                     cycle, dist_count-1);
        end else if (dist_timer > 0) begin
            dist_timer <= dist_timer - 1;
        end

        if (compute_start && compute_ready) begin
            if (compute_timer >= 0) $fatal(1, "overlapping compute command");
            compute_timer <= 11;
            compute_count <= compute_count + 1;
            $display("QTRACE cycle=%0d component=pingpong event=compute_start chunk=%0d slot=%0d points=%0d",
                     cycle, compute_count, compute_slot, compute_point_count);
            if (compute_merge_count != 8'd5)
                $fatal(1, "merge count mismatch");
        end else if (compute_timer == 0) begin
            compute_done <= 1'b1;
            compute_timer <= -1;
            $display("QTRACE cycle=%0d component=pingpong event=compute_done chunk=%0d",
                     cycle, compute_count-1);
        end else if (compute_timer > 0) begin
            compute_timer <= compute_timer - 1;
        end

        if (dist_wr_cmd_valid && dist_wr_cmd_ready) begin
            if (write_timer >= 0) $fatal(1, "overlapping write command");
            write_timer <= 6;
            write_count <= write_count + 1;
            $display("QTRACE cycle=%0d component=pingpong event=dist_write_cmd chunk=%0d addr=%0d bytes=%0d",
                     cycle, write_count, dist_wr_cmd_addr, dist_wr_cmd_bytes);
            if (dist_wr_cmd_addr < bucket_dist_addr)
                $fatal(1, "MDT write address escaped distance region");
        end else if (write_timer == 0) begin
            dist_wr_done <= 1'b1;
            write_timer <= -1;
            $display("QTRACE cycle=%0d component=pingpong event=dist_write_done chunk=%0d",
                     cycle, write_count-1);
        end else if (write_timer > 0) begin
            write_timer <= write_timer - 1;
        end

        if (bucket_done) begin
            if (coord_count != 3 || dist_count != 3 ||
                write_count != 3 || compute_count != 3) begin
                $display("CHUNK_CTRL_FAIL coord=%0d dist=%0d write=%0d compute=%0d",
                         coord_count, dist_count, write_count, compute_count);
                $fatal(1);
            end
            $display("QTRACE cycle=%0d component=pingpong event=bucket_done chunks=3", cycle);
            $display("CHUNK_CTRL_PASS cycles=%0d", cycle);
            $finish;
        end
    end

    initial begin
        repeat (4) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        bucket_valid <= 1'b1;
        @(posedge clk);
        bucket_valid <= 1'b0;
        repeat (1000) @(posedge clk);
        $fatal(1, "chunk controller timeout");
    end
endmodule
