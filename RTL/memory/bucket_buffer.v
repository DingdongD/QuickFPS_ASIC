module bucket_buffer #(
    parameter DEPTH = 512,
    parameter AW    = $clog2(DEPTH),
    parameter WIDTH = 394
)(
    input  wire             clk,
    input  wire [AW-1:0]    raddr,
    output wire [WIDTH-1:0] rdata,
    input  wire             wen,
    input  wire [AW-1:0]    waddr,
    input  wire [WIDTH-1:0] wdata
);
    // Functional reference memory.  The asynchronous read keeps the existing
    // Bucket-Engine interface compact; ASIC integration may replace this file
    // with a macro wrapper plus a one-cycle request/response adapter.
    reg [WIDTH-1:0] mem [0:DEPTH-1];

    assign rdata = mem[raddr];

    always @(posedge clk) begin
        if (wen)
            mem[waddr] <= wdata;
    end
endmodule
