`timescale 1ns/1ps
module tb_bucket_decision_pipe;
    localparam BIDX_W=4;
    localparam PIDX_W=8;
    localparam MCNT_W=4;
    localparam ENTRY_W=368+PIDX_W+MCNT_W;
    localparam FIFO_DEPTH=8;
    localparam E_MINX=0, E_MINY=32, E_MINZ=64;
    localparam E_MAXX=96, E_MAXY=128, E_MAXZ=160;
    localparam E_FX=240, E_FY=272, E_FZ=304, E_FDIST=336;
    localparam E_FIDX=368;

    reg clk=1'b0;
    always #0.5 clk=~clk;
    reg rst_n=1'b0;
    reg in_valid=1'b0;
    wire in_ready;
    wire [BIDX_W-1:0] in_bid;
    reg [ENTRY_W-1:0] in_entry={ENTRY_W{1'b0}};
    reg in_first_iter=1'b1;
    wire out_valid;
    reg out_ready=1'b1;
    wire [1:0] out_action;
    wire [BIDX_W-1:0] out_bid;
    wire [ENTRY_W-1:0] out_entry;
    wire [31:0] out_dlb, out_far_distance;

    integer cycle=0;
    integer sent=0;
    integer received=0;
    integer first_accept=-1;
    integer first_output=-1;
    integer stall_cycles=0;

    assign in_bid = sent[BIDX_W-1:0];

    bucket_decision_pipe #(
        .BIDX_W(BIDX_W), .PIDX_W(PIDX_W), .MCNT_W(MCNT_W),
        .ENTRY_W(ENTRY_W), .FIFO_DEPTH(FIFO_DEPTH)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .in_valid(in_valid), .in_ready(in_ready),
        .in_bid(in_bid), .in_entry(in_entry),
        .in_first_iter(in_first_iter),
        .sample_x(32'h00000000),
        .sample_y(32'h00000000),
        .sample_z(32'h00000000),
        .out_valid(out_valid), .out_ready(out_ready),
        .out_action(out_action), .out_bid(out_bid), .out_entry(out_entry),
        .out_dlb(out_dlb), .out_far_distance(out_far_distance)
    );

    always @* begin
        in_entry = {ENTRY_W{1'b0}};
        in_entry[E_MINX +:32] = 32'h00000000;
        in_entry[E_MINY +:32] = 32'h00000000;
        in_entry[E_MINZ +:32] = 32'h00000000;
        in_entry[E_MAXX +:32] = 32'h3f800000;
        in_entry[E_MAXY +:32] = 32'h3f800000;
        in_entry[E_MAXZ +:32] = 32'h3f800000;
        in_entry[E_FX +:32] = 32'h3f800000;
        in_entry[E_FY +:32] = 32'h00000000;
        in_entry[E_FZ +:32] = 32'h00000000;
        in_entry[E_FDIST +:32] = 32'h3f800000;
        in_entry[E_FIDX +:PIDX_W] = {{(PIDX_W-BIDX_W){1'b0}}, in_bid};
    end

    always @(posedge clk) begin
        cycle <= cycle + 1;
        if (cycle >= 12 && cycle < 25)
            out_ready <= 1'b0;
        else
            out_ready <= (cycle % 5 != 0);

        if (rst_n)
            in_valid <= sent < 16;

        if (in_valid && in_ready) begin
            if (first_accept < 0) first_accept <= cycle;
            sent <= sent + 1;
            $display("BPIPE_ACCEPT %0d %0d", cycle, in_bid);
        end else if (in_valid && !in_ready) begin
            stall_cycles <= stall_cycles + 1;
        end

        if (out_valid && out_ready) begin
            if (first_output < 0) first_output <= cycle;
            if (out_bid != received[BIDX_W-1:0]) begin
                $display("BPIPE_ORDER_FAIL got=%0d expected=%0d", out_bid, received);
                $fatal(1);
            end
            if (out_action != 2'd2)
                $fatal(1, "first-iteration bucket must issue");
            $display("BPIPE_OUTPUT %0d %0d", cycle, out_bid);
            received <= received + 1;
            if (received + 1 == 16) begin
                if (first_output - first_accept < 4)
                    $fatal(1, "bucket decision latency shorter than CD pipe");
                if (stall_cycles == 0)
                    $fatal(1, "credit backpressure was not exercised");
                $display("BUCKET_DECISION_PIPE_PASS cycles=%0d stalls=%0d",
                         cycle, stall_cycles);
                $finish;
            end
        end
    end

    initial begin
        $dumpfile("build/activity/bucket_decision_pipe.vcd");
        $dumpvars(0, tb_bucket_decision_pipe.dut);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        repeat (1000) @(posedge clk);
        $fatal(1, "bucket decision pipeline timeout");
    end
endmodule
