module axi_burst_reader #(
    parameter ADDR_W = 64,
    parameter DATA_W = 256,
    parameter LEN_W  = 32,
    parameter MAX_BURST_BEATS = 16
)(
    input  wire                 clk,
    input  wire                 rst_n,

    input  wire                 cmd_valid,
    output wire                 cmd_ready,
    input  wire [ADDR_W-1:0]    cmd_addr,
    input  wire [LEN_W-1:0]     cmd_bytes,
    output reg                  done,
    output reg                  busy,

    output reg                  m_axi_arvalid,
    input  wire                 m_axi_arready,
    output reg  [ADDR_W-1:0]    m_axi_araddr,
    output reg  [7:0]           m_axi_arlen,
    output wire [2:0]           m_axi_arsize,
    output wire [1:0]           m_axi_arburst,

    input  wire                 m_axi_rvalid,
    output wire                 m_axi_rready,
    input  wire [DATA_W-1:0]    m_axi_rdata,
    input  wire                 m_axi_rlast,
    input  wire [1:0]           m_axi_rresp,

    output wire                 out_valid,
    input  wire                 out_ready,
    output wire [DATA_W-1:0]    out_data,
    output wire                 out_last,
    output reg  [LEN_W-1:0]     bytes_completed
);
    localparam BUS_BYTES = DATA_W / 8;
    localparam SIZE_CODE = $clog2(BUS_BYTES);
    localparam S_IDLE  = 2'd0;
    localparam S_ADDR  = 2'd1;
    localparam S_DATA  = 2'd2;
    reg [1:0] state;

    reg [ADDR_W-1:0] address;
    reg [LEN_W-1:0] remaining;
    reg [LEN_W-1:0] burst_bytes;
    reg [8:0] burst_beats;
    reg [8:0] beat_count;
    reg error_seen;

    wire [12:0] bytes_to_4k = 13'd4096 - {1'b0, address[11:0]};
    wire [LEN_W-1:0] max_burst_bytes = MAX_BURST_BEATS * BUS_BYTES;
    wire [LEN_W-1:0] bounded_4k =
        (remaining < bytes_to_4k) ? remaining : bytes_to_4k;
    wire [LEN_W-1:0] next_burst_bytes =
        (bounded_4k < max_burst_bytes) ? bounded_4k : max_burst_bytes;
    wire [LEN_W:0] rounded_bytes = next_burst_bytes + BUS_BYTES - 1;
    wire [8:0] next_burst_beats = rounded_bytes / BUS_BYTES;

    assign cmd_ready = (state == S_IDLE);
    assign m_axi_arsize = SIZE_CODE[2:0];
    assign m_axi_arburst = 2'b01;
    assign m_axi_rready = (state == S_DATA) && out_ready;
    assign out_valid = (state == S_DATA) && m_axi_rvalid;
    assign out_data = m_axi_rdata;
    assign out_last = m_axi_rvalid && m_axi_rlast &&
                      (remaining <= burst_bytes);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            done <= 1'b0;
            busy <= 1'b0;
            m_axi_arvalid <= 1'b0;
            m_axi_araddr <= {ADDR_W{1'b0}};
            m_axi_arlen <= 8'd0;
            address <= {ADDR_W{1'b0}};
            remaining <= {LEN_W{1'b0}};
            burst_bytes <= {LEN_W{1'b0}};
            burst_beats <= 9'd0;
            beat_count <= 9'd0;
            bytes_completed <= {LEN_W{1'b0}};
            error_seen <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: begin
                    busy <= 1'b0;
                    m_axi_arvalid <= 1'b0;
                    if (cmd_valid && cmd_ready) begin
                        address <= cmd_addr;
                        remaining <= cmd_bytes;
                        bytes_completed <= {LEN_W{1'b0}};
                        error_seen <= 1'b0;
                        busy <= 1'b1;
                        if (cmd_bytes == {LEN_W{1'b0}}) begin
                            done <= 1'b1;
                        end else begin
                            state <= S_ADDR;
                        end
                    end
                end

                S_ADDR: begin
                    busy <= 1'b1;
                    if (!m_axi_arvalid) begin
                        m_axi_araddr <= address;
                        m_axi_arlen <= next_burst_beats[7:0] - 1'b1;
                        burst_bytes <= next_burst_bytes;
                        burst_beats <= next_burst_beats;
                        beat_count <= 9'd0;
                        m_axi_arvalid <= 1'b1;
                    end
                    if (m_axi_arvalid && m_axi_arready) begin
                        m_axi_arvalid <= 1'b0;
                        state <= S_DATA;
                    end
                end

                S_DATA: begin
                    busy <= 1'b1;
                    if (m_axi_rvalid && m_axi_rready) begin
                        beat_count <= beat_count + 1'b1;
                        if (m_axi_rresp != 2'b00)
                            error_seen <= 1'b1;
                        if (m_axi_rlast) begin
                            if (beat_count + 1'b1 != burst_beats)
                                error_seen <= 1'b1;
                            address <= address + burst_bytes;
                            bytes_completed <= bytes_completed + burst_bytes;
                            if (remaining <= burst_bytes) begin
                                remaining <= {LEN_W{1'b0}};
                                busy <= 1'b0;
                                done <= 1'b1;
                                state <= S_IDLE;
                            end else begin
                                remaining <= remaining - burst_bytes;
                                state <= S_ADDR;
                            end
                        end
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

    // synopsys translate_off
    initial begin
        if (DATA_W % 8 != 0 || (BUS_BYTES & (BUS_BYTES-1)) != 0)
            $fatal(1, "axi_burst_reader: DATA_W must be a power-of-two byte width");
        if (MAX_BURST_BEATS < 1 || MAX_BURST_BEATS > 256)
            $fatal(1, "axi_burst_reader: MAX_BURST_BEATS must be in [1,256]");
    end
    always @(posedge clk)
        if (done && error_seen)
            $display("axi_burst_reader: completed with AXI protocol/response error");
    // synopsys translate_on
endmodule
