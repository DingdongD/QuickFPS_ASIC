#!/usr/bin/env python3
import os
import random
import re
import struct
import subprocess
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "RTL"
TB = ROOT / "tb"
REPORTS = ROOT / "reports"


def f32_bits(x: float) -> int:
    return struct.unpack(">I", struct.pack(">f", np.float32(x)))[0]


def bits_f32(x: int) -> np.float32:
    return np.float32(struct.unpack(">f", struct.pack(">I", x & 0xFFFFFFFF))[0])


def rtl_files():
    return [str(p) for p in sorted(RTL.rglob("*.v"))]


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    path.write_text(normalized)


def gen_fp32_ops_tb(n=128):
    random.seed(7)
    cases = []
    vals = [0.0, 0.125, 0.25, 0.5, 1.0, 1.5, 2.0, 3.25, 4.5, 8.0, 16.0]
    for _ in range(n):
        a = random.choice(vals) * random.choice([1.0, -1.0])
        b = random.choice(vals) * random.choice([1.0, -1.0])
        if abs(a + b) < 1e-8:
            b = np.float32(b + 0.25)
        cases.append((a, b))

    body = []
    for i, (a, b) in enumerate(cases):
        body.append(f"""
        a = 32'h{f32_bits(a):08x}; b = 32'h{f32_bits(b):08x}; #1;
        $display("FPCASE %0d %08x %08x %08x %08x %08x", {i}, a, b, add_y, sub_y, mul_y);
        """)
    tb = f"""
`timescale 1ns/1ps
module tb_fp32_ops;
    reg [31:0] a, b;
    wire [31:0] add_y, sub_y, mul_y;
    fp32_add u_add(.a(a), .b(b), .result(add_y));
    fp32_sub u_sub(.a(a), .b(b), .result(sub_y));
    fp32_mul u_mul(.a(a), .b(b), .result(mul_y));
    initial begin
        {"".join(body)}
        $finish;
    end
endmodule
"""
    return tb, cases


def check_fp32_ops():
    tb, cases = gen_fp32_ops_tb()
    tb_path = TB / "tb_fp32_ops_auto.v"
    write_text(tb_path, tb)
    exe = REPORTS / "tb_fp32_ops_auto.vvp"
    comp = run(["iverilog", "-g2012", "-o", str(exe), str(tb_path)] + rtl_files())
    if comp.returncode != 0:
        return {"pass": False, "compile_log": comp.stdout}
    sim = run(["vvp", str(exe)])
    max_abs = {"add": 0.0, "sub": 0.0, "mul": 0.0}
    max_rel = {"add": 0.0, "sub": 0.0, "mul": 0.0}
    mismatches = 0
    for line in sim.stdout.splitlines():
        if not line.startswith("FPCASE"):
            continue
        _, idx_s, a_s, b_s, add_s, sub_s, mul_s = line.split()
        idx = int(idx_s)
        a, b = cases[idx]
        got = {
            "add": bits_f32(int(add_s, 16)),
            "sub": bits_f32(int(sub_s, 16)),
            "mul": bits_f32(int(mul_s, 16)),
        }
        ref = {
            "add": np.float32(np.float32(a) + np.float32(b)),
            "sub": np.float32(np.float32(a) - np.float32(b)),
            "mul": np.float32(np.float32(a) * np.float32(b)),
        }
        for op in got:
            ae = float(abs(np.float32(got[op] - ref[op])))
            re = ae / max(float(abs(ref[op])), 1e-9)
            max_abs[op] = max(max_abs[op], ae)
            max_rel[op] = max(max_rel[op], re)
            if ae > 1e-4 and re > 1e-4:
                mismatches += 1
    return {
        "pass": mismatches == 0,
        "cases": len(cases),
        "mismatches": mismatches,
        "max_abs": max_abs,
        "max_rel": max_rel,
        "sim_log": sim.stdout,
    }


def gen_bucket_cd_tb(n=96):
    random.seed(11)
    cases = []
    for i in range(n):
        minx, miny, minz = [random.uniform(0.0, 4.0) for _ in range(3)]
        maxx = minx + random.uniform(0.25, 3.0)
        maxy = miny + random.uniform(0.25, 3.0)
        maxz = minz + random.uniform(0.25, 3.0)
        qx = random.uniform(-1.0, 8.0)
        qy = random.uniform(-1.0, 8.0)
        qz = random.uniform(-1.0, 8.0)
        fpx = random.uniform(0.0, 8.0)
        fpy = random.uniform(0.0, 8.0)
        fpz = random.uniform(0.0, 8.0)
        cases.append((i, qx, qy, qz, minx, miny, minz, maxx, maxy, maxz, fpx, fpy, fpz))
    drive = []
    for c in cases:
        i, qx, qy, qz, minx, miny, minz, maxx, maxy, maxz, fpx, fpy, fpz = c
        drive.append(f"""
        in_valid <= 1'b1; meta_in <= 16'h{i:04x};
        qx <= 32'h{f32_bits(qx):08x}; qy <= 32'h{f32_bits(qy):08x}; qz <= 32'h{f32_bits(qz):08x};
        minx <= 32'h{f32_bits(minx):08x}; miny <= 32'h{f32_bits(miny):08x}; minz <= 32'h{f32_bits(minz):08x};
        maxx <= 32'h{f32_bits(maxx):08x}; maxy <= 32'h{f32_bits(maxy):08x}; maxz <= 32'h{f32_bits(maxz):08x};
        fpx <= 32'h{f32_bits(fpx):08x}; fpy <= 32'h{f32_bits(fpy):08x}; fpz <= 32'h{f32_bits(fpz):08x};
        @(posedge clk);
        """)
    tb = f"""
`timescale 1ns/1ps
module tb_bucket_cd_auto;
    reg clk = 0; always #5 clk = ~clk;
    reg rst_n = 0, in_valid = 0;
    reg [15:0] meta_in = 0;
    reg [31:0] qx=0, qy=0, qz=0, minx=0, miny=0, minz=0, maxx=0, maxy=0, maxz=0, fpx=0, fpy=0, fpz=0;
    wire out_valid;
    wire [15:0] out_meta;
    wire [31:0] out_dlb, out_d;
    bucket_cd #(.META_W(16)) dut(
        .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .meta_in(meta_in),
        .qx(qx), .qy(qy), .qz(qz), .minx(minx), .miny(miny), .minz(minz),
        .maxx(maxx), .maxy(maxy), .maxz(maxz), .fpx(fpx), .fpy(fpy), .fpz(fpz),
        .out_valid(out_valid), .out_meta(out_meta), .out_dlb(out_dlb), .out_d(out_d));
    always @(posedge clk) if (out_valid) $display("CDOUT %0d %08x %08x", out_meta, out_dlb, out_d);
    initial begin
        repeat (3) @(posedge clk); rst_n <= 1'b1; @(posedge clk);
        {"".join(drive)}
        in_valid <= 1'b0;
        repeat (8) @(posedge clk);
        $finish;
    end
endmodule
"""
    return tb, cases


def check_bucket_cd():
    tb, cases = gen_bucket_cd_tb()
    tb_path = TB / "tb_bucket_cd_auto.v"
    write_text(tb_path, tb)
    exe = REPORTS / "tb_bucket_cd_auto.vvp"
    comp = run(["iverilog", "-g2012", "-o", str(exe), str(tb_path)] + rtl_files())
    if comp.returncode != 0:
        return {"pass": False, "compile_log": comp.stdout}
    sim = run(["vvp", str(exe)])
    got = {}
    for line in sim.stdout.splitlines():
        if line.startswith("CDOUT"):
            _, idx_s, dlb_s, d_s = line.split()
            got[int(idx_s)] = (bits_f32(int(dlb_s, 16)), bits_f32(int(d_s, 16)))
    max_abs_dlb = 0.0
    max_abs_d = 0.0
    mismatches = 0
    for c in cases:
        i, qx, qy, qz, minx, miny, minz, maxx, maxy, maxz, fpx, fpy, fpz = c
        gapx = max(minx - qx, 0.0, qx - maxx)
        gapy = max(miny - qy, 0.0, qy - maxy)
        gapz = max(minz - qz, 0.0, qz - maxz)
        dlb_ref = np.float32(np.float32(gapx * gapx) + np.float32(gapy * gapy) + np.float32(gapz * gapz))
        d_ref = np.float32(np.float32((qx-fpx)*(qx-fpx)) + np.float32((qy-fpy)*(qy-fpy)) + np.float32((qz-fpz)*(qz-fpz)))
        if i not in got:
            mismatches += 1
            continue
        dlb_got, d_got = got[i]
        edlb = float(abs(dlb_got - dlb_ref))
        ed = float(abs(d_got - d_ref))
        max_abs_dlb = max(max_abs_dlb, edlb)
        max_abs_d = max(max_abs_d, ed)
        if edlb > 2e-2 or ed > 5e-2:
            mismatches += 1
    return {
        "pass": mismatches == 0,
        "cases": len(cases),
        "observed": len(got),
        "mismatches": mismatches,
        "max_abs_dlb": max_abs_dlb,
        "max_abs_d": max_abs_d,
        "sim_log": sim.stdout,
    }


def gen_pe_tb(n=96):
    random.seed(23)
    mx, my, mz = 1.25, 2.5, 3.75
    cases = []
    for i in range(n):
        x = random.uniform(-2.0, 6.0)
        y = random.uniform(-2.0, 6.0)
        z = random.uniform(-2.0, 6.0)
        in_dist = random.uniform(0.1, 128.0)
        cases.append((i, x, y, z, in_dist))
    drive = []
    for i, x, y, z, in_dist in cases:
        drive.append(f"""
        in_valid <= 1'b1; in_idx <= 11'd{i};
        in_x <= 32'h{f32_bits(x):08x}; in_y <= 32'h{f32_bits(y):08x}; in_z <= 32'h{f32_bits(z):08x};
        in_dist <= 32'h{f32_bits(in_dist):08x};
        @(posedge clk);
        """)
    tb = f"""
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
        m_x_in <= 32'h{f32_bits(mx):08x}; m_y_in <= 32'h{f32_bits(my):08x}; m_z_in <= 32'h{f32_bits(mz):08x};
        m_load <= 1'b1; @(posedge clk); m_load <= 1'b0;
        {"".join(drive)}
        in_valid <= 1'b0;
        repeat (12) @(posedge clk);
        $finish;
    end
endmodule
"""
    return tb, cases, (mx, my, mz)


def check_pe():
    tb, cases, merge = gen_pe_tb()
    tb_path = TB / "tb_pe_auto.v"
    write_text(tb_path, tb)
    exe = REPORTS / "tb_pe_auto.vvp"
    comp = run(["iverilog", "-g2012", "-o", str(exe), str(tb_path)] + rtl_files())
    if comp.returncode != 0:
        return {"pass": False, "compile_log": comp.stdout}
    sim = run(["vvp", str(exe)])
    got = {}
    for line in sim.stdout.splitlines():
        if line.startswith("PEOUT"):
            _, idx_s, dist_s = line.split()
            got[int(idx_s)] = bits_f32(int(dist_s, 16))
    mx, my, mz = merge
    mismatches = 0
    max_abs = 0.0
    for i, x, y, z, in_dist in cases:
        d = np.float32(np.float32((x-mx)*(x-mx)) + np.float32((y-my)*(y-my)) + np.float32((z-mz)*(z-mz)))
        ref = np.float32(min(np.float32(in_dist), d))
        if i not in got:
            mismatches += 1
            continue
        err = float(abs(got[i] - ref))
        max_abs = max(max_abs, err)
        if err > 5e-2:
            mismatches += 1
    return {
        "pass": mismatches == 0,
        "cases": len(cases),
        "observed": len(got),
        "mismatches": mismatches,
        "max_abs": max_abs,
        "sim_log": sim.stdout,
    }


def check_point_engine_top_cycles():
    tb_path = TB / "tb_point_engine_top_cycle.v"
    exe = REPORTS / "tb_point_engine_top_cycle.vvp"
    comp = run(["iverilog", "-g2012", "-s", "tb_point_engine_top_cycle",
                "-o", str(exe)] + rtl_files() + [str(tb_path)])
    if comp.returncode != 0:
        return {"pass": False, "compile_log": comp.stdout}
    sim = run(["vvp", str(exe)])
    passed = sim.returncode == 0 and "PTOP_CYCLE_PASS" in sim.stdout
    latency = None
    for line in sim.stdout.splitlines():
        if line.startswith("PTOP_PUSH"):
            fields = line.split()
            latency = int(fields[3])
    return {
        "pass": passed,
        "latency_cycles": latency,
        "shape": "R=4,L=4,num_points=48,merge_count=3",
        "sim_log": sim.stdout,
    }


def check_bucket_engine_strict():
    tb_path = TB / "tb_bucket_engine_gate.v"
    exe = REPORTS / "tb_bucket_engine_gate.vvp"
    comp = run(["iverilog", "-g2012", "-s", "tb_bucket_engine_gate",
                "-o", str(exe)] + rtl_files() + [str(tb_path)])
    if comp.returncode != 0:
        return {"pass": False, "compile_log": comp.stdout}
    sim = run(["vvp", str(exe)])
    passed = sim.returncode == 0 and "BENG_STRICT_PASS" in sim.stdout
    match = re.search(
        r"BENG_STRICT_PASS\s+latency_cycles=(\d+)\s+requests=(\d+)\s+responses=(\d+)",
        sim.stdout,
    )
    return {
        "pass": passed,
        "latency_cycles": int(match.group(1)) if match else None,
        "requests": int(match.group(2)) if match else None,
        "responses": int(match.group(3)) if match else None,
        "sim_log": sim.stdout,
    }


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    results = {
        "fp32_ops": check_fp32_ops(),
        "bucket_cd": check_bucket_cd(),
        "pe": check_pe(),
        "point_engine_top_cycles": check_point_engine_top_cycles(),
        "bucket_engine_strict": check_bucket_engine_strict(),
    }
    out = ROOT / "reports" / "quickfps_golden_summary.txt"
    lines = []
    ok = True
    for name, res in results.items():
        ok = ok and bool(res.get("pass"))
        lines.append(f"[{name}] pass={res.get('pass')} details={{{', '.join(f'{k}={v}' for k, v in res.items() if k not in ('sim_log', 'compile_log'))}}}")
        if "compile_log" in res:
            lines.append(res["compile_log"])
    write_text(out, "\n".join(lines) + "\n")
    print(out)
    print("\n".join(lines))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
