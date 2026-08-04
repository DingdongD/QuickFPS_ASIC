module axi_burst_writer #(
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

    input  wire                 in_valid,
    output wire                 in_ready,
    input  wire [DATA_W-1:0]    in_data,

    output reg                  m_axi_awvalid,
    input  wire                 m_axi_awready,
    output reg  [ADDR_W-1:0]    m_axi_awaddr,
    output reg  [7:0]           m_axi_awlen,
    output wire [2:0]           m_axi_awsize,
    output wire [1:0]           m_axi_awburst,

    output wire                 m_axi_wvalid,
    input  wire                 m_axi_wready,
    output wire [DATA_W-1:0]    m_axi_wdata,
    output wire [DATA_W/8-1:0]  m_axi_wstrb,
    output wire                 m_axi_wlast,

    input  wire                 m_axi_bvalid,
    output wire                 m_axi_bready,
    input  wire [1:0]           m_axi_bresp,
    output reg  [LEN_W-1:0]     bytes_completed
);
    localparam BUS_BYTES = DATA_W / 8;
    localparam SIZE_CODE = $clog2(BUS_BYTES);
    localparam S_IDLE = 3'd0;
    localparam S_ADDR = 3'd1;
    localparam S_DATA = 3'd2;
    localparam S_RESP = 3'd3;
    reg [2:0] state;

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
    wire [LEN_W-1:0] bytes_before_last =
        (burst_beats > 1) ? ((burst_beats - 1'b1) * BUS_BYTES) : 0;
    wire [LEN_W-1:0] final_valid_bytes =
        burst_bytes - bytes_before_last;

    reg [DATA_W/8-1:0] final_strobe;
    integer k;
    always @* begin
        final_strobe = {DATA_W/8{1'b0}};
        for (k = 0; k < BUS_BYTES; k = k + 1)
            if (k < final_valid_bytes)
                final_strobe[k] = 1'b1;
    end

    assign cmd_ready = (state == S_IDLE);
    assign m_axi_awsize = SIZE_CODE[2:0];
    assign m_axi_awburst = 2'b01;
    assign in_ready = (state == S_DATA) && m_axi_wready;
    assign m_axi_wvalid = (state == S_DATA) && in_valid;
    assign m_axi_wdata = in_data;
    assign m_axi_wlast = (state == S_DATA) &&
                         (beat_count + 1'b1 == burst_beats);
    assign m_axi_wstrb = m_axi_wlast ? final_strobe :
                         {DATA_W/8{1'b1}};
    assign m_axi_bready = (state == S_RESP);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            done <= 1'b0;
            busy <= 1'b0;
            m_axi_awvalid <= 1'b0;
            m_axi_awaddr <= {ADDR_W{1'b0}};
            m_axi_awlen <= 8'd0;
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
                    m_axi_awvalid <= 1'b0;
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
                    if (!m_axi_awvalid) begin
                        m_axi_awaddr <= address;
                        m_axi_awlen <= next_burst_beats[7:0] - 1'b1;
                        burst_bytes <= next_burst_bytes;
                        burst_beats <= next_burst_beats;
                        beat_count <= 9'd0;
                        m_axi_awvalid <= 1'b1;
                    end
                    if (m_axi_awvalid && m_axi_awready) begin
                        m_axi_awvalid <= 1'b0;
                        state <= S_DATA;
                    end
                end

                S_DATA: begin
                    busy <= 1'b1;
                    if (m_axi_wvalid && m_axi_wready) begin
                        beat_count <= beat_count + 1'b1;
                        if (m_axi_wlast)
                            state <= S_RESP;
                    end
                end

                S_RESP: begin
                    busy <= 1'b1;
                    if (m_axi_bvalid && m_axi_bready) begin
                        if (m_axi_bresp != 2'b00)
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

                default: state <= S_IDLE;
            endcase
        end
    end

    // synopsys translate_off
    initial begin
        if (DATA_W % 8 != 0 || (BUS_BYTES & (BUS_BYTES-1)) != 0)
            $fatal(1, "axi_burst_writer: DATA_W must be a power-of-two byte width");
        if (MAX_BURST_BEATS < 1 || MAX_BURST_BEATS > 256)
            $fatal(1, "axi_burst_writer: MAX_BURST_BEATS must be in [1,256]");
    end
    always @(posedge clk)
        if (done && error_seen)
            $display("axi_burst_writer: completed with AXI response error");
    // synopsys translate_on
endmodule
