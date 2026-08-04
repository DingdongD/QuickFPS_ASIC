module merge_buffer #(
    parameter BUCKETS = 512,
    parameter BIDX_W  = $clog2(BUCKETS),
    parameter CAP     = 32,
    parameter MCNT_W  = 8
)(
    input  wire              clk,
    input  wire              rst_n,
    input  wire              wen,
    input  wire              clr,
    input  wire [BIDX_W-1:0] addr,
    input  wire [95:0]       wdata,
    input  wire [BIDX_W-1:0] rd_bid,
    input  wire [7:0]        rd_slot,
    output wire [95:0]       rdata,
    output wire [MCNT_W-1:0] rd_count
);
    localparam TOTAL = BUCKETS * CAP;
    reg [95:0] mem [0:TOTAL-1];
    reg [MCNT_W-1:0] count [0:BUCKETS-1];

    wire [MCNT_W-1:0] selected_count = count[rd_bid];
    wire [$clog2(TOTAL)-1:0] rd_linear = rd_bid * CAP + rd_slot;
    assign rdata = (rd_slot < selected_count && rd_slot < CAP) ?
                   mem[rd_linear] : 96'h0;
    assign rd_count = selected_count;

    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < BUCKETS; i = i + 1)
                count[i] <= {MCNT_W{1'b0}};
        end else begin
            if (clr) begin
                count[addr] <= {MCNT_W{1'b0}};
            end else if (wen && count[addr] < CAP) begin
                mem[addr * CAP + count[addr]] <= wdata;
                count[addr] <= count[addr] + 1'b1;
            end
        end
    end

    // synopsys translate_off
    always @(posedge clk)
        if (rst_n && wen && count[addr] >= CAP)
            $fatal(1, "merge_buffer overflow: bucket=%0d count=%0d cap=%0d",
                   addr, count[addr], CAP);
    // synopsys translate_on
endmodule
