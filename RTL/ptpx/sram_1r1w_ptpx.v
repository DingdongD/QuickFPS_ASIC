module sram_1r1w_ptpx (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         rd_valid,
    output wire         rd_ready,
    input  wire [7:0]   rd_addr,
    output wire         rsp_valid,
    output wire [127:0] rsp_data,
    input  wire         wr_valid,
    output wire         wr_ready,
    input  wire [7:0]   wr_addr,
    input  wire [127:0] wr_data,
    input  wire [15:0]  wr_strb
);
    // Fixed wrapper used for gate-level VCD/PTPX characterization.  The
    // adapter/control power is directly reusable; replace the inferred array
    // with a compiler macro and add macro power separately for final SRAM PPA.
    sram_1r1w_sync #(
        .WIDTH(128),
        .DEPTH(256),
        .AW(8),
        .READ_LATENCY(2)
    ) u_sram (
        .clk(clk), .rst_n(rst_n),
        .rd_valid(rd_valid), .rd_ready(rd_ready), .rd_addr(rd_addr),
        .rsp_valid(rsp_valid), .rsp_data(rsp_data),
        .wr_valid(wr_valid), .wr_ready(wr_ready), .wr_addr(wr_addr),
        .wr_data(wr_data), .wr_strb(wr_strb)
    );
endmodule
