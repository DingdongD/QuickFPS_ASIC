module coord_buffer #(
    parameter DEPTH  = 131072,
    parameter PIDX_W = $clog2(DEPTH),
    parameter R      = 4
)(
    input  wire                clk,
    input  wire                host_wen,
    input  wire [PIDX_W-1:0]   host_waddr,
    input  wire [95:0]         host_wdata,
    input  wire [PIDX_W-1:0]   rd_base,
    output wire [R*96-1:0]     rd_data
);
    reg [95:0] mem [0:DEPTH-1];

    genvar g;
    generate
        for (g = 0; g < R; g = g + 1) begin : g_read
            wire [PIDX_W:0] addr_ext = {1'b0, rd_base} + g;
            assign rd_data[g*96 +: 96] =
                (addr_ext < DEPTH) ? mem[addr_ext[PIDX_W-1:0]] : 96'h0;
        end
    endgenerate

    always @(posedge clk) begin
        if (host_wen)
            mem[host_waddr] <= host_wdata;
    end
endmodule
