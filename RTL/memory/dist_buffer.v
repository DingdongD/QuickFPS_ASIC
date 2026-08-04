module dist_buffer #(
    parameter DEPTH  = 131072,
    parameter PIDX_W = $clog2(DEPTH),
    parameter R      = 4
)(
    input  wire                clk,
    input  wire                host_wen,
    input  wire [PIDX_W-1:0]   host_waddr,
    input  wire [31:0]         host_wdata,
    input  wire [PIDX_W-1:0]   rd_base,
    output wire [R*32-1:0]     rd_data,
    input  wire [R-1:0]        core_wstrb,
    input  wire [PIDX_W-1:0]   core_wbase,
    input  wire [R*32-1:0]     core_wdata
);
    reg [31:0] mem [0:DEPTH-1];

    genvar g;
    generate
        for (g = 0; g < R; g = g + 1) begin : g_read
            wire [PIDX_W:0] addr_ext = {1'b0, rd_base} + g;
            assign rd_data[g*32 +: 32] =
                (addr_ext < DEPTH) ? mem[addr_ext[PIDX_W-1:0]] : 32'h0;
        end
    endgenerate

    integer i;
    always @(posedge clk) begin
        if (host_wen)
            mem[host_waddr] <= host_wdata;

        for (i = 0; i < R; i = i + 1) begin
            if (core_wstrb[i])
                mem[core_wbase + i] <= core_wdata[i*32 +: 32];
        end
    end
endmodule
