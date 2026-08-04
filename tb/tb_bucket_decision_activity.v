`timescale 1ns/1ps
module tb_bucket_decision_activity;
    localparam BIDX_W=9;
    localparam PIDX_W=18;
    localparam MCNT_W=8;
    localparam ENTRY_W=368+PIDX_W+MCNT_W;
    localparam E_MINX=0, E_MINY=32, E_MINZ=64;
    localparam E_MAXX=96, E_MAXY=128, E_MAXZ=160;
    localparam E_FX=240, E_FY=272, E_FZ=304, E_FDIST=336;
    localparam E_FIDX=368;

    reg clk=1'b0;
    always #0.5 clk=~clk;
    reg rst_n=1'b0;
    reg in_valid=1'b0;
    wire in_ready;
    reg [BIDX_W-1:0] in_bid=0;
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
    integer stalls=0;

    bucket_decision_pipe dut (
        .clk(clk), .rst_n(rst_n),
        .in_valid(in_valid), .in_ready(in_ready),
        .in_bid(in_bid), .in_entry(in_entry), .in_first_iter(in_first_iter),
        .sample_x(32'h3e800000),
        .sample_y(32'h3f000000),
        .sample_z(32'h3f400000),
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
        in_entry[E_FY +:32] = 32'h3f000000;
        in_entry[E_FZ +:32] = 32'h3e800000;
        in_entry[E_FDIST +:32] = 32'h3f000000;
        in_entry[E_FIDX +:PIDX_W] = in_bid;
    end

    always @(posedge clk) begin
        cycle <= cycle + 1;
        out_ready <= (cycle % 9 != 0) && !(cycle >= 20 && cycle < 33);
        if (rst_n) begin
            in_valid <= sent < 64;
            in_bid <= sent[BIDX_W-1:0];
            in_first_iter <= (sent < 32);
        end
        if (in_valid && in_ready)
            sent <= sent + 1;
        else if (in_valid)
            stalls <= stalls + 1;

        if (out_valid && out_ready) begin
            if (out_bid != received[BIDX_W-1:0])
                $fatal(1, "bucket activity ordering mismatch");
            received <= received + 1;
            if (received + 1 == 64) begin
                if (stalls == 0)
                    $fatal(1, "bucket decision backpressure not exercised");
                $display("BUCKET_DECISION_ACTIVITY_PASS cycles=%0d stalls=%0d",
                         cycle, stalls);
                $finish;
            end
        end
    end

    initial begin
        $dumpfile("build/activity/bucket_decision_pipe.vcd");
        $dumpvars(0, tb_bucket_decision_activity.dut);
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        repeat (5000) @(posedge clk);
        $fatal(1, "bucket decision activity timeout");
    end
endmodule
