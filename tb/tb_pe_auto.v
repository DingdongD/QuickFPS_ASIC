
`timescale 1ns/1ps
module tb_pe_auto;
    reg clk = 0; always #5 clk = ~clk;
    reg rst_n = 0, m_load = 0, in_valid = 0;
    reg [10:0] in_idx = 0;
    reg [31:0] m_x_in=0, m_y_in=0, m_z_in=0, in_x=0, in_y=0, in_z=0, in_dist=0;
    wire out_valid;
    wire [10:0] out_idx;
    wire [31:0] out_x, out_y, out_z, out_dist;
    pe dut(
        .clk(clk), .rst_n(rst_n), .m_load(m_load),
        .m_x_in(m_x_in), .m_y_in(m_y_in), .m_z_in(m_z_in),
        .in_valid(in_valid), .in_idx(in_idx), .in_x(in_x), .in_y(in_y), .in_z(in_z), .in_dist(in_dist),
        .out_valid(out_valid), .out_idx(out_idx), .out_x(out_x), .out_y(out_y), .out_z(out_z), .out_dist(out_dist));
    always @(posedge clk) if (out_valid) $display("PEOUT %0d %08x", out_idx, out_dist);
    initial begin
        repeat (3) @(posedge clk); rst_n <= 1'b1; @(posedge clk);
        m_x_in <= 32'h3fa00000; m_y_in <= 32'h40200000; m_z_in <= 32'h40700000;
        m_load <= 1'b1; @(posedge clk); m_load <= 1'b0;

        in_valid <= 1'b1; in_idx <= 11'd0;
        in_x <= 32'h40acc3f8; in_y <= 32'h40b2d7d4; in_z <= 32'h40a47683;
        in_dist <= 32'h412c93ff;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd1;
        in_x <= 32'h402f1e31; in_y <= 32'h3fb1ead7; in_z <= 32'h400f67b2;
        in_dist <= 32'h41862040;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd2;
        in_x <= 32'hbeed9463; in_y <= 32'h3fc73e4c; in_z <= 32'hbe6d3f42;
        in_dist <= 32'h426931e2;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd3;
        in_x <= 32'hbfe6a37d; in_y <= 32'hbfa82ad7; in_z <= 32'h406b8632;
        in_dist <= 32'h4257e921;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd4;
        in_x <= 32'h400677f4; in_y <= 32'h4077ea41; in_z <= 32'h3f5f397c;
        in_dist <= 32'h40eec25a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd5;
        in_x <= 32'h40887965; in_y <= 32'h402da198; in_z <= 32'h4050d9ef;
        in_dist <= 32'h429f0cb4;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd6;
        in_x <= 32'h40b8821b; in_y <= 32'h3f66ffc4; in_z <= 32'h40828160;
        in_dist <= 32'h423d04c6;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd7;
        in_x <= 32'h4024e351; in_y <= 32'h40523144; in_z <= 32'h3f03df7d;
        in_dist <= 32'h41310ce7;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd8;
        in_x <= 32'h3fe571ab; in_y <= 32'h406f926d; in_z <= 32'h402e6465;
        in_dist <= 32'h426550f4;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd9;
        in_x <= 32'h4048e5d5; in_y <= 32'hbf0b3444; in_z <= 32'hbf1259a5;
        in_dist <= 32'h4225db96;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd10;
        in_x <= 32'h4090dd16; in_y <= 32'hbedeca4d; in_z <= 32'hbf8af4a0;
        in_dist <= 32'h414b6236;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd11;
        in_x <= 32'hbfd821e7; in_y <= 32'h3e516c90; in_z <= 32'h402548e9;
        in_dist <= 32'h42d2202a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd12;
        in_x <= 32'h3f257d03; in_y <= 32'h3f750d1f; in_z <= 32'h3e9da1bd;
        in_dist <= 32'h421c544a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd13;
        in_x <= 32'h40870fa6; in_y <= 32'h401915ac; in_z <= 32'h3d89edd9;
        in_dist <= 32'h415cd33e;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd14;
        in_x <= 32'h4088a7b6; in_y <= 32'h406a0eb5; in_z <= 32'h40941cdb;
        in_dist <= 32'h41f4593f;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd15;
        in_x <= 32'h40174907; in_y <= 32'h40ab32c1; in_z <= 32'h402f75d1;
        in_dist <= 32'h42f20ce2;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd16;
        in_x <= 32'hbf2973b8; in_y <= 32'h40b99a06; in_z <= 32'hbfc6bcf5;
        in_dist <= 32'h42555700;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd17;
        in_x <= 32'hbfe81395; in_y <= 32'h408f3f8a; in_z <= 32'h405fd962;
        in_dist <= 32'h42f94816;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd18;
        in_x <= 32'h408e121a; in_y <= 32'h40b2e666; in_z <= 32'h4013c2df;
        in_dist <= 32'h42fcfc6e;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd19;
        in_x <= 32'h407f7ed0; in_y <= 32'h3f44e663; in_z <= 32'h40b971b3;
        in_dist <= 32'h424145d4;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd20;
        in_x <= 32'hbee82fb2; in_y <= 32'hbfb24d48; in_z <= 32'h3fdd240b;
        in_dist <= 32'h41ca01cf;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd21;
        in_x <= 32'h40aefefa; in_y <= 32'h40b350ef; in_z <= 32'hbe8b76da;
        in_dist <= 32'h415568d3;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd22;
        in_x <= 32'h400ed527; in_y <= 32'hbf247ed7; in_z <= 32'h40165913;
        in_dist <= 32'h42d0200c;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd23;
        in_x <= 32'h3cc8b1c3; in_y <= 32'h3fafdfa7; in_z <= 32'h40a69f6b;
        in_dist <= 32'h4263e79a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd24;
        in_x <= 32'h3f3e0176; in_y <= 32'h40a46faa; in_z <= 32'h4090524f;
        in_dist <= 32'h42e52ffe;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd25;
        in_x <= 32'h40602007; in_y <= 32'h3fa68670; in_z <= 32'h4062d3e7;
        in_dist <= 32'h42d477c6;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd26;
        in_x <= 32'h40476e23; in_y <= 32'hbdbda884; in_z <= 32'h3eb95b65;
        in_dist <= 32'h4251f5b3;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd27;
        in_x <= 32'h40858be1; in_y <= 32'h401d3afc; in_z <= 32'h40199168;
        in_dist <= 32'h42d3a111;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd28;
        in_x <= 32'hbf90f376; in_y <= 32'h404331b3; in_z <= 32'h3f28f6f8;
        in_dist <= 32'h428f4877;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd29;
        in_x <= 32'h4095d976; in_y <= 32'hbc57fa35; in_z <= 32'h40b396b0;
        in_dist <= 32'h4122658e;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd30;
        in_x <= 32'h401fc141; in_y <= 32'h401568c4; in_z <= 32'hbdf47089;
        in_dist <= 32'h428faa3c;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd31;
        in_x <= 32'h3fe20640; in_y <= 32'h3fcc629e; in_z <= 32'h406fcf87;
        in_dist <= 32'h3f1aab89;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd32;
        in_x <= 32'h3f823aa6; in_y <= 32'h40891d25; in_z <= 32'hbf5d76c0;
        in_dist <= 32'h42de141c;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd33;
        in_x <= 32'hbebe17c8; in_y <= 32'h405cbcb3; in_z <= 32'hbf1d5b71;
        in_dist <= 32'h4266462f;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd34;
        in_x <= 32'h3fb0b102; in_y <= 32'hbfac3cb1; in_z <= 32'h406632d8;
        in_dist <= 32'h42760eb8;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd35;
        in_x <= 32'h4060c5de; in_y <= 32'h4014094a; in_z <= 32'h401c9b1a;
        in_dist <= 32'h4286c880;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd36;
        in_x <= 32'h3ec3c435; in_y <= 32'h40a614b5; in_z <= 32'hbfa78938;
        in_dist <= 32'h42e0703b;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd37;
        in_x <= 32'h409d0bfb; in_y <= 32'h3ffdc0fc; in_z <= 32'h4086e614;
        in_dist <= 32'h42ac727b;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd38;
        in_x <= 32'h4035cc33; in_y <= 32'h3eaa80bb; in_z <= 32'h3f0ea410;
        in_dist <= 32'h42332495;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd39;
        in_x <= 32'h3ed5b20d; in_y <= 32'h40b5af13; in_z <= 32'h3f3aef6c;
        in_dist <= 32'h4246abb3;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd40;
        in_x <= 32'h3fada0fe; in_y <= 32'h409105bf; in_z <= 32'h3fe9399a;
        in_dist <= 32'h428dd990;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd41;
        in_x <= 32'h3d33a229; in_y <= 32'h3e65f2db; in_z <= 32'hbfa4c61d;
        in_dist <= 32'h41df195d;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd42;
        in_x <= 32'h3de38b20; in_y <= 32'h409a2e68; in_z <= 32'h400143bc;
        in_dist <= 32'h41638017;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd43;
        in_x <= 32'h3fd9d404; in_y <= 32'hbf842b1a; in_z <= 32'h4021ce47;
        in_dist <= 32'h42629885;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd44;
        in_x <= 32'h409bb887; in_y <= 32'h3d97ee16; in_z <= 32'h4099d218;
        in_dist <= 32'h41fe259f;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd45;
        in_x <= 32'h40bb8c98; in_y <= 32'h4044b32f; in_z <= 32'hbfd44bcb;
        in_dist <= 32'h42ceacf1;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd46;
        in_x <= 32'h3e5218c9; in_y <= 32'h3f65e105; in_z <= 32'hbf53cc00;
        in_dist <= 32'h42d66a6c;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd47;
        in_x <= 32'hbfa37500; in_y <= 32'h4079fe13; in_z <= 32'h3f9538f5;
        in_dist <= 32'h42ae005a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd48;
        in_x <= 32'h3eb065de; in_y <= 32'hbfafd83e; in_z <= 32'h40aa4894;
        in_dist <= 32'h42a7af7c;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd49;
        in_x <= 32'hbf247d7b; in_y <= 32'h40b9e7b5; in_z <= 32'h40a96ce3;
        in_dist <= 32'h41bba380;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd50;
        in_x <= 32'hbfec7113; in_y <= 32'h4038d4b8; in_z <= 32'hbf63046f;
        in_dist <= 32'h42bb6ae0;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd51;
        in_x <= 32'h3fe020ef; in_y <= 32'h406b0a75; in_z <= 32'h4023bbb2;
        in_dist <= 32'h42c558cc;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd52;
        in_x <= 32'h40925637; in_y <= 32'h4034afc5; in_z <= 32'h402ecbba;
        in_dist <= 32'h42279f02;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd53;
        in_x <= 32'hbf6d6236; in_y <= 32'hbfa14a8a; in_z <= 32'h409b60ac;
        in_dist <= 32'h41d3abbc;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd54;
        in_x <= 32'h3fb4cd4f; in_y <= 32'h3f08b458; in_z <= 32'h403d4165;
        in_dist <= 32'h4288a148;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd55;
        in_x <= 32'h409bea06; in_y <= 32'h3fbe81a1; in_z <= 32'h3f652ece;
        in_dist <= 32'h42a6c816;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd56;
        in_x <= 32'h407d56c3; in_y <= 32'h40aceb47; in_z <= 32'h3efd4221;
        in_dist <= 32'h42e2f5f2;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd57;
        in_x <= 32'h40bb3f3c; in_y <= 32'h40bb7cd6; in_z <= 32'hbf77687e;
        in_dist <= 32'h4242dd7a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd58;
        in_x <= 32'h4086242e; in_y <= 32'h4094be13; in_z <= 32'hbfd78937;
        in_dist <= 32'h424a83e4;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd59;
        in_x <= 32'h4072c491; in_y <= 32'h40821e93; in_z <= 32'h4011f78d;
        in_dist <= 32'h41d83d26;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd60;
        in_x <= 32'h3fa09237; in_y <= 32'hbfc40cc5; in_z <= 32'h3f068458;
        in_dist <= 32'h425b0ab4;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd61;
        in_x <= 32'h4092ac31; in_y <= 32'h402dbd45; in_z <= 32'h3fa84f7b;
        in_dist <= 32'h41fc7054;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd62;
        in_x <= 32'h3f05b0ce; in_y <= 32'h40576c9d; in_z <= 32'h3fc8264a;
        in_dist <= 32'h41b1f0b2;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd63;
        in_x <= 32'h40925d10; in_y <= 32'h4026b70b; in_z <= 32'h40b7af56;
        in_dist <= 32'h42896843;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd64;
        in_x <= 32'h403f02c1; in_y <= 32'h3fb5e963; in_z <= 32'h403770ef;
        in_dist <= 32'h42eb3ce5;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd65;
        in_x <= 32'h40bb35d4; in_y <= 32'h4052689e; in_z <= 32'h3fb890a8;
        in_dist <= 32'h4101dea4;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd66;
        in_x <= 32'h40971743; in_y <= 32'h3f90d0cd; in_z <= 32'h3f87a062;
        in_dist <= 32'h40ecf44b;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd67;
        in_x <= 32'hbfdd0d6d; in_y <= 32'h3f8fe8c6; in_z <= 32'h40b987e0;
        in_dist <= 32'h42bda3a8;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd68;
        in_x <= 32'h406ae877; in_y <= 32'h40563e93; in_z <= 32'h3e3b607f;
        in_dist <= 32'h41ad5ddf;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd69;
        in_x <= 32'h403467ab; in_y <= 32'hbfbee9be; in_z <= 32'h402d185f;
        in_dist <= 32'h4283cdca;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd70;
        in_x <= 32'h4015c257; in_y <= 32'hbf83c0cb; in_z <= 32'hbfbac732;
        in_dist <= 32'h4272817b;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd71;
        in_x <= 32'hbf55dcce; in_y <= 32'h40486cc1; in_z <= 32'h3ef3dc00;
        in_dist <= 32'h429ef5f6;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd72;
        in_x <= 32'h40800dca; in_y <= 32'h40367edb; in_z <= 32'h40102bad;
        in_dist <= 32'h41cab305;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd73;
        in_x <= 32'h3f470b15; in_y <= 32'h40ba5acd; in_z <= 32'h3e181e7b;
        in_dist <= 32'h4211dcc0;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd74;
        in_x <= 32'h3ff91f75; in_y <= 32'h40178746; in_z <= 32'h408a6e39;
        in_dist <= 32'h42177247;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd75;
        in_x <= 32'h40b67be2; in_y <= 32'hbfe93d65; in_z <= 32'h408a5533;
        in_dist <= 32'h4291efc9;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd76;
        in_x <= 32'h40a6b2b6; in_y <= 32'hbf4685ae; in_z <= 32'h4060e171;
        in_dist <= 32'h42f27f3e;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd77;
        in_x <= 32'h4055885a; in_y <= 32'hbf8cea69; in_z <= 32'h40abc26c;
        in_dist <= 32'h42f83bb5;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd78;
        in_x <= 32'hbf8e8964; in_y <= 32'h4093c7d9; in_z <= 32'hbfaec476;
        in_dist <= 32'h4127f50b;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd79;
        in_x <= 32'h408b9dac; in_y <= 32'h407098d6; in_z <= 32'h40b50a38;
        in_dist <= 32'h42a1d8f0;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd80;
        in_x <= 32'h4005fd49; in_y <= 32'h3e34c90a; in_z <= 32'h40254d4f;
        in_dist <= 32'h42fe121f;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd81;
        in_x <= 32'h404b17c0; in_y <= 32'h40a023b6; in_z <= 32'hbed74094;
        in_dist <= 32'h42bc345a;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd82;
        in_x <= 32'h4076ab61; in_y <= 32'hbfb771e3; in_z <= 32'h4091f897;
        in_dist <= 32'h41b4f4bb;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd83;
        in_x <= 32'hbe85c463; in_y <= 32'hbfc15187; in_z <= 32'h40534981;
        in_dist <= 32'h4192661b;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd84;
        in_x <= 32'h40b9c756; in_y <= 32'hbffff54e; in_z <= 32'h408f3ac1;
        in_dist <= 32'h42c26522;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd85;
        in_x <= 32'h40237b49; in_y <= 32'h4024daa6; in_z <= 32'h408c484e;
        in_dist <= 32'h42a2fb42;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd86;
        in_x <= 32'hbf629155; in_y <= 32'h408bfe20; in_z <= 32'h3f54be2e;
        in_dist <= 32'h4295870c;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd87;
        in_x <= 32'h40065dd6; in_y <= 32'h40a76ed6; in_z <= 32'h3fa84e2d;
        in_dist <= 32'h42da8139;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd88;
        in_x <= 32'hbfac3b0b; in_y <= 32'h3f1bfe58; in_z <= 32'h40575585;
        in_dist <= 32'h429cbc7e;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd89;
        in_x <= 32'h409512de; in_y <= 32'hbeac6613; in_z <= 32'h408ddf8a;
        in_dist <= 32'h42cbb83d;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd90;
        in_x <= 32'hbf5b4a00; in_y <= 32'hbf61a11b; in_z <= 32'h402aa4a6;
        in_dist <= 32'h42f9c3a9;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd91;
        in_x <= 32'h403a3afd; in_y <= 32'h3fb63965; in_z <= 32'h400383fa;
        in_dist <= 32'h42cf4874;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd92;
        in_x <= 32'h400b692d; in_y <= 32'h4012d217; in_z <= 32'h402fc2fa;
        in_dist <= 32'h42eea144;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd93;
        in_x <= 32'h408ce6de; in_y <= 32'h4096d268; in_z <= 32'h3e04c03f;
        in_dist <= 32'h4299b7cb;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd94;
        in_x <= 32'h4092b5c4; in_y <= 32'h406fb23b; in_z <= 32'h40b3aa3c;
        in_dist <= 32'h42ea4f9d;
        @(posedge clk);

        in_valid <= 1'b1; in_idx <= 11'd95;
        in_x <= 32'hbf7a9df5; in_y <= 32'h400432ff; in_z <= 32'h3f5cb216;
        in_dist <= 32'h41d2b209;
        @(posedge clk);

        in_valid <= 1'b0;
        repeat (12) @(posedge clk);
        $finish;
    end
endmodule
