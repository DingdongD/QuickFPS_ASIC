module sram_1r1w_sync #(
    parameter WIDTH = 32,
    parameter DEPTH = 1024,
    parameter AW = $clog2(DEPTH),
    parameter READ_LATENCY = 1
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             rd_valid,
    output wire             rd_ready,
    input  wire [AW-1:0]    rd_addr,
    output wire             rsp_valid,
    output wire [WIDTH-1:0] rsp_data,
    input  wire             wr_valid,
    output wire             wr_ready,
    input  wire [AW-1:0]    wr_addr,
    input  wire [WIDTH-1:0] wr_data,
    input  wire [WIDTH/8-1:0] wr_strb
);
    localparam BYTE_LANES = WIDTH / 8;
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [READ_LATENCY-1:0] valid_pipe;
    reg [WIDTH-1:0] data_pipe [0:READ_LATENCY-1];
    integer i;
    integer b;

    assign rd_ready = 1'b1;
    assign wr_ready = 1'b1;
    assign rsp_valid = valid_pipe[READ_LATENCY-1];
    assign rsp_data = data_pipe[READ_LATENCY-1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_pipe <= {READ_LATENCY{1'b0}};
            for (i = 0; i < READ_LATENCY; i = i + 1)
                data_pipe[i] <= {WIDTH{1'b0}};
        end else begin
            valid_pipe[0] <= rd_valid && rd_ready;
            if (rd_valid && rd_ready)
                data_pipe[0] <= mem[rd_addr];
            for (i = 1; i < READ_LATENCY; i = i + 1) begin
                valid_pipe[i] <= valid_pipe[i-1];
                data_pipe[i] <= data_pipe[i-1];
            end
            if (wr_valid && wr_ready) begin
                for (b = 0; b < BYTE_LANES; b = b + 1)
                    if (wr_strb[b])
                        mem[wr_addr][b*8 +: 8] <= wr_data[b*8 +: 8];
            end
        end
    end

    // synopsys translate_off
    initial begin
        if (WIDTH % 8 != 0)
            $fatal(1, "sram_1r1w_sync: WIDTH must be byte-aligned");
        if (READ_LATENCY < 1)
            $fatal(1, "sram_1r1w_sync: READ_LATENCY must be >= 1");
    end
    // synopsys translate_on
endmodule
