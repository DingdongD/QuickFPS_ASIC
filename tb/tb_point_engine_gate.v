`timescale 1ns/1ps
module tb_point_engine_gate;
    reg clk = 0; always #0.5 clk = ~clk;
    reg rst_n = 0;
    reg clr = 0;
    reg [3:0] m_load = 0;
    reg [127:0] m_x = 0, m_y = 0, m_z = 0;
    reg [3:0] in_valid = 0;
    reg [43:0] in_idx = 0;
    reg [127:0] in_x = 0, in_y = 0, in_z = 0, in_dist = 0;
    wire [10:0] far_idx;
    wire [31:0] far_dist;
    wire far_valid;
    wire [3:0] o_row_valid;
    wire [43:0] o_row_idx;
    wire [127:0] o_row_dist;
    integer cycle_count = 0;

    point_engine #(.L(4), .R(4), .LIDX_W(11)) dut(
        .clk(clk), .rst_n(rst_n), .clr(clr),
        .m_load(m_load), .m_x(m_x), .m_y(m_y), .m_z(m_z),
        .in_valid(in_valid), .in_idx(in_idx),
        .in_x(in_x), .in_y(in_y), .in_z(in_z), .in_dist(in_dist),
        .far_idx(far_idx), .far_dist(far_dist), .far_valid(far_valid),
        .o_row_valid(o_row_valid), .o_row_idx(o_row_idx), .o_row_dist(o_row_dist)
    );

    initial begin
        $dumpfile("activity_1ghz/point_engine_gate.vcd");
        $dumpvars(0, tb_point_engine_gate.dut);
    end

    always @(posedge clk) begin
        cycle_count <= cycle_count + 1;
        if (|in_valid)      $display("PENG_IN %0d", cycle_count);
        if (o_row_valid[0]) $display("PENG_ROW %0d %08x %0d", o_row_idx[0 +: 11], o_row_dist[0 +: 32], cycle_count);
        if (o_row_valid[1]) $display("PENG_ROW %0d %08x %0d", o_row_idx[11 +: 11], o_row_dist[32 +: 32], cycle_count);
        if (o_row_valid[2]) $display("PENG_ROW %0d %08x %0d", o_row_idx[22 +: 11], o_row_dist[64 +: 32], cycle_count);
        if (o_row_valid[3]) $display("PENG_ROW %0d %08x %0d", o_row_idx[33 +: 11], o_row_dist[96 +: 32], cycle_count);
        if (far_valid)      $display("PENG_FAR %0d %08x %0d", far_idx, far_dist, cycle_count);
    end

    initial begin
        repeat (3) @(posedge clk); rst_n <= 1'b1; @(posedge clk);
        clr <= 1'b1; @(posedge clk); clr <= 1'b0;

        m_x <= 128'h0000000000000000000000003f67b4dc;
        m_y <= 128'h0000000000000000000000003e1d4840;
        m_z <= 128'h000000000000000000000000be2de458;
        m_load <= 4'b0001;
        @(posedge clk);

        m_x <= 128'h000000000000000040646d3c00000000;
        m_y <= 128'h00000000000000003ff1e18800000000;
        m_z <= 128'h0000000000000000401cd7ab00000000;
        m_load <= 4'b0010;
        @(posedge clk);

        m_x <= 128'h000000003fe1f5440000000000000000;
        m_y <= 128'h000000003f6aefb80000000000000000;
        m_z <= 128'h00000000402a1ea80000000000000000;
        m_load <= 4'b0100;
        @(posedge clk);

        m_x <= 128'h3ff0e9f5000000000000000000000000;
        m_y <= 128'h4039fcb0000000000000000000000000;
        m_z <= 128'h4013b4b7000000000000000000000000;
        m_load <= 4'b1000;
        @(posedge clk);

        m_load <= 4'b0000;

        in_valid <= 4'b1111;
        in_idx   <= 44'h00600800800;
        in_x     <= 128'h40974ec8bfc312a84072434c4096dc3c;
        in_y     <= 128'hbe8bc8644088c8d2bf28f01c3fc1f0a2;
        in_z     <= 128'h4073d577bfde339e404f2ef7bf427573;
        in_dist  <= 128'h42bb9ce742ddfda7429f1b8d419b21a5;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h00e01802804;
        in_x     <= 128'h4098b604403d63864060b125bf7ffe03;
        in_y     <= 128'h3ed299e5403766de40bae19a405703fd;
        in_z     <= 128'hbf552e66bf0b142bbfc92f8ebf814312;
        in_dist  <= 128'h42ab164142e353ef4223655b42e9d3ff;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h01602804808;
        in_x     <= 128'h404f6bb83fb3e15ebfe9d0b53fa0f6b7;
        in_y     <= 128'h3f1330d6407d2774bf6b9fb74053a145;
        in_z     <= 128'hbf63b68440145eff3fd56b543ff91a57;
        in_dist  <= 128'h410a5a2c42e16e1a42ba8ee8424ac15b;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h01e0380680c;
        in_x     <= 128'h409930f0404f95acbf900bfebfd77410;
        in_y     <= 128'h40b63083407fcde440522dc5409ccbbd;
        in_z     <= 128'hbd871c5e4037d641bf7a8fda409fe539;
        in_dist  <= 128'h426081504256caea42e3a82142c07994;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h02604808810;
        in_x     <= 128'h3f84ed993e5cde5640b7b6a1407782ff;
        in_y     <= 128'h40a2971d40a5bf423e548446405c22e0;
        in_z     <= 128'h4080499c3f1b1d17be9d902c3fa477b1;
        in_dist  <= 128'h42bb87c642ecbdcb42afce614266f528;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h02e0580a814;
        in_x     <= 128'hbf86a3b7bf4240c440554690be9228f9;
        in_y     <= 128'h40bf5da53f21ef87bfbe16dcbf2f9c4c;
        in_z     <= 128'h40328daebe3129b2bdd19514bfe03b36;
        in_dist  <= 128'h42b6aefa42ad3d91429160ab41ba996d;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h0360680c818;
        in_x     <= 128'h407494984046d01040926b00401ae862;
        in_y     <= 128'h4088a0fb4006a64ebfe1709c3ffdc424;
        in_z     <= 128'hbfb68f2d404ca596402dd4c640b87ee7;
        in_dist  <= 128'h4282c0a241b6e72342f11aeb42e4d872;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h03e0780e81c;
        in_x     <= 128'h402cbe484039539240a7fc844030c217;
        in_y     <= 128'h3eda032940945b3e3eec9f4f3f50ee64;
        in_z     <= 128'h408c286f409e71f6bf4933a7405d0771;
        in_dist  <= 128'h42b1318e420fcbd442daae0c42ec0dba;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h04608810820;
        in_x     <= 128'h406ed30f40b0a288bf0a41dabdb371f7;
        in_y     <= 128'h406a9608409373f83fe59e7440001152;
        in_z     <= 128'hbfe48e14bfc86106bfb62dab403033de;
        in_dist  <= 128'h42c2a76542d37ac8427e06ec41f028f7;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h04e09812824;
        in_x     <= 128'hbfe4508f4007120cbf1f367dbedf812d;
        in_y     <= 128'h4092d6c6bf4fe186409e1a2f408d9441;
        in_z     <= 128'h3e2b5efe404f7052be66e1bb3f14601d;
        in_dist  <= 128'h40532fd5428821ac42df8130423c5b1c;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h0560a814828;
        in_x     <= 128'h3ff015504022bbd8400dcb284084304f;
        in_y     <= 128'h40810eff40710a43402c403440744062;
        in_z     <= 128'h408d845dbef713db4061043d3f8b08e3;
        in_dist  <= 128'h42da872041ba8f49427b2c1741c04fb4;
        @(posedge clk);

        in_valid <= 4'b1111;
        in_idx   <= 44'h05e0b81682c;
        in_x     <= 128'h3f7708844080a0d5bfbb9a293fc17a6c;
        in_y     <= 128'h3f4e789f3f7a53a74095d5c0406d68da;
        in_z     <= 128'h409d2abe408b7f4140bff118bf934dd4;
        in_dist  <= 128'h41b2ca524131c8ba42ab998942479f71;
        @(posedge clk);

        in_valid <= 4'b0000;
        repeat (96) @(posedge clk);
        $finish;
    end
endmodule
