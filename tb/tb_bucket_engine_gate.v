`timescale 1ns/1ps
module tb_bucket_engine_gate;
    localparam BIDX_W = 9;
    localparam PIDX_W = 18;
    localparam NUMP_W = 16;
    localparam ADDR_W = 32;
    localparam MCNT_W = 8;
    localparam ENTRY_W = 368 + PIDX_W + MCNT_W;
    localparam BF_W = BIDX_W + ADDR_W + NUMP_W + 96 + MCNT_W;
    localparam FP_W = BIDX_W + 96 + 32 + PIDX_W;

    localparam E_MINX = 0;
    localparam E_MINY = 32;
    localparam E_MINZ = 64;
    localparam E_MAXX = 96;
    localparam E_MAXY = 128;
    localparam E_MAXZ = 160;
    localparam E_PTR = 192;
    localparam E_NUMP = 224;
    localparam E_FX = 240;
    localparam E_FY = 272;
    localparam E_FZ = 304;
    localparam E_FDIST = 336;
    localparam E_FIDX = 368;
    localparam E_MCNT = E_FIDX + PIDX_W;

    reg clk = 1'b0;
    always #0.5 clk = ~clk;

    reg rst_n = 1'b0;
    reg start = 1'b0;
    wire busy;
    wire done;
    reg [PIDX_W-1:0] sample_n = 18'd3;
    reg [BIDX_W-1:0] bucket_m = 9'd3;
    reg [31:0] p0x = 32'h00000000;
    reg [31:0] p0y = 32'h00000000;
    reg [31:0] p0z = 32'h00000000;
    reg [PIDX_W-1:0] p0idx = 18'd0;

    wire [BIDX_W-1:0] bb_raddr;
    wire [ENTRY_W-1:0] bb_rdata;
    wire bb_wen;
    wire [BIDX_W-1:0] bb_waddr;
    wire [ENTRY_W-1:0] bb_wdata;
    wire mb_wen;
    wire mb_clr;
    wire [BIDX_W-1:0] mb_addr;
    wire [95:0] mb_wdata;
    wire bkt_empty;
    wire [BF_W-1:0] bkt_rdata;
    wire bkt_ren;
    wire fp_full;
    reg fp_wen = 1'b0;
    reg [FP_W-1:0] fp_wdata = {FP_W{1'b0}};
    wire res_wen;
    wire [PIDX_W-1:0] res_addr;
    wire [95+PIDX_W:0] res_wdata;

    reg [ENTRY_W-1:0] bb_mem [0:3];
    assign bb_rdata = bb_mem[bb_raddr[1:0]];

    reg pending = 1'b0;
    reg [BIDX_W-1:0] pending_bid = {BIDX_W{1'b0}};
    reg response_iter = 1'b0;
    integer response_wait = 0;
    integer cycle_count = 0;
    integer start_cycle = -1;
    integer request_count = 0;
    integer response_count = 0;
    integer result_count = 0;
    integer defer_count = 0;

    assign bkt_ren = !bkt_empty && !pending;

    function [31:0] response_x;
        input [BIDX_W-1:0] bid;
        begin
            case (bid)
                9'd0: response_x = 32'h3f800000;
                9'd1: response_x = 32'h40000000;
                9'd2: response_x = 32'h40400000;
                default: response_x = 32'h40800000;
            endcase
        end
    endfunction

    function [31:0] response_dist;
        input iter;
        input [BIDX_W-1:0] bid;
        begin
            if (!iter) begin
                case (bid)
                    9'd0: response_dist = 32'h3f800000;
                    9'd1: response_dist = 32'h40800000;
                    9'd2: response_dist = 32'h41100000;
                    default: response_dist = 32'h41800000;
                endcase
            end else begin
                case (bid)
                    9'd1: response_dist = 32'h40800000;
                    9'd2: response_dist = 32'h3f800000;
                    default: response_dist = 32'h00000000;
                endcase
            end
        end
    endfunction

    function [PIDX_W-1:0] response_idx;
        input [BIDX_W-1:0] bid;
        begin
            response_idx = bid * 18'd16 + 18'd3;
        end
    endfunction

    bucket_engine dut (
        .clk(clk), .rst_n(rst_n), .start(start), .busy(busy), .done(done),
        .sample_n(sample_n), .bucket_m(bucket_m),
        .p0x(p0x), .p0y(p0y), .p0z(p0z), .p0idx(p0idx),
        .bb_raddr(bb_raddr), .bb_rdata(bb_rdata),
        .bb_wen(bb_wen), .bb_waddr(bb_waddr), .bb_wdata(bb_wdata),
        .mb_wen(mb_wen), .mb_clr(mb_clr), .mb_addr(mb_addr),
        .mb_wdata(mb_wdata), .bkt_empty(bkt_empty), .bkt_rdata(bkt_rdata),
        .bkt_ren(bkt_ren), .fp_full(fp_full),
        .fp_wen(fp_wen), .fp_wdata(fp_wdata),
        .res_wen(res_wen), .res_addr(res_addr), .res_wdata(res_wdata)
    );

    initial begin
        $dumpfile("activity_1ghz/bucket_engine_gate.vcd");
        $dumpvars(0, tb_bucket_engine_gate.dut);
    end

    task init_entry;
        input integer bid;
        input [31:0] fx;
        input [31:0] fdist;
        reg [ENTRY_W-1:0] entry;
        begin
            entry = {ENTRY_W{1'b0}};
            if (bid == 0) begin
                entry[E_MINX +: 32] = 32'h00000000;
                entry[E_MAXX +: 32] = 32'h40a00000;
            end else begin
                entry[E_MINX +: 32] = fx;
                entry[E_MAXX +: 32] = fx;
            end
            entry[E_MINY +: 32] = 32'h00000000;
            entry[E_MINZ +: 32] = 32'h00000000;
            entry[E_MAXY +: 32] = 32'h00000000;
            entry[E_MAXZ +: 32] = 32'h00000000;
            entry[E_PTR +: ADDR_W] = bid * 32'd16;
            entry[E_NUMP +: NUMP_W] = 16'd16;
            entry[E_FX +: 32] = fx;
            entry[E_FY +: 32] = 32'h00000000;
            entry[E_FZ +: 32] = 32'h00000000;
            entry[E_FDIST +: 32] = fdist;
            entry[E_FIDX +: PIDX_W] = response_idx(bid[BIDX_W-1:0]);
            entry[E_MCNT +: MCNT_W] = {MCNT_W{1'b0}};
            bb_mem[bid] = entry;
        end
    endtask

    always @(posedge clk) begin
        cycle_count <= cycle_count + 1;
        fp_wen <= 1'b0;

        if (start && !busy && start_cycle < 0) begin
            start_cycle <= cycle_count;
            $display("BENG_START %0d", cycle_count);
        end

        if (bb_wen)
            bb_mem[bb_waddr[1:0]] <= bb_wdata;

        if (bkt_ren && !bkt_empty) begin
            pending <= 1'b1;
            pending_bid <= bkt_rdata[0 +: BIDX_W];
            response_wait <= 2;
            request_count <= request_count + 1;
            $display("BENG_REQ %0d %0d %0d", cycle_count,
                     response_iter, bkt_rdata[0 +: BIDX_W]);
        end else if (pending && response_wait > 0) begin
            response_wait <= response_wait - 1;
        end else if (pending && !fp_full) begin
            fp_wen <= 1'b1;
            fp_wdata <= {pending_bid,
                         response_idx(pending_bid),
                         response_dist(response_iter, pending_bid),
                         32'h00000000, 32'h00000000,
                         response_x(pending_bid)};
            pending <= 1'b0;
            response_count <= response_count + 1;
            $display("BENG_RESP %0d %0d %0d", cycle_count,
                     response_iter, pending_bid);
        end

        if (mb_wen) begin
            defer_count <= defer_count + 1;
            $display("BENG_DEFER %0d %0d", cycle_count, mb_addr);
        end

        if (res_wen) begin
            result_count <= result_count + 1;
            $display("BENG_RESULT %0d %0d %h", cycle_count, res_addr, res_wdata);
            if (res_addr == 18'd1) begin
                if (res_wdata[0 +: 32] !== 32'h40800000 ||
                    res_wdata[96 +: PIDX_W] !== 18'd51)
                    $fatal(1, "BENG result 1 mismatch");
                response_iter <= 1'b1;
            end
            if (res_addr == 18'd2) begin
                if (res_wdata[0 +: 32] !== 32'h40000000 ||
                    res_wdata[96 +: PIDX_W] !== 18'd19)
                    $fatal(1, "BENG result 2 mismatch");
            end
        end

        if (done) begin
            if (start_cycle < 0)
                $fatal(1, "BENG done without accepted start");
            if (request_count != 7 || response_count != 7 ||
                result_count != 3 || defer_count != 1)
                $fatal(1, "BENG count mismatch req=%0d resp=%0d res=%0d defer=%0d",
                       request_count, response_count, result_count, defer_count);
            $display("BENG_STRICT_PASS latency_cycles=%0d requests=%0d responses=%0d",
                     cycle_count - start_cycle, request_count, response_count);
            $finish;
        end
    end

    initial begin
        init_entry(0, 32'h3f800000, 32'h3f800000);
        init_entry(1, 32'h40000000, 32'h40800000);
        init_entry(2, 32'h40400000, 32'h41100000);
        init_entry(3, 32'h40800000, 32'h41800000);

        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        repeat (2) @(posedge clk);
        start <= 1'b1;
        @(posedge clk);
        start <= 1'b0;

        repeat (512) @(posedge clk);
        $fatal(1, "BENG timeout");
    end
endmodule
