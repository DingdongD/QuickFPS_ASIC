module result_buffer #(
    parameter DEPTH  = 32768,
    parameter PIDX_W = $clog2(DEPTH),
    parameter WIDTH  = 96 + PIDX_W
)(
    input  wire             clk,
    input  wire             wen,
    input  wire [PIDX_W-1:0] waddr,
    input  wire [WIDTH-1:0] wdata,
    input  wire [PIDX_W-1:0] raddr,
    output wire [WIDTH-1:0] rdata
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];

    assign rdata = mem[raddr];

    always @(posedge clk) begin
        if (wen)
            mem[waddr] <= wdata;
    end
endmodule
