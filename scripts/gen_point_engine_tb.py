#!/usr/bin/env python3
import json
import random
import struct
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TB = ROOT / "tb"
REPORTS = ROOT / "reports"


def f32_bits(x):
    return struct.unpack(">I", struct.pack(">f", np.float32(x)))[0]


def bits_f32(x):
    return np.float32(struct.unpack(">f", struct.pack(">I", x & 0xFFFFFFFF))[0])


def pack_words(words):
    value = 0
    for i, word in enumerate(words):
        value |= (word & 0xFFFFFFFF) << (32 * i)
    return value


def pack_idx(words, width):
    value = 0
    mask = (1 << width) - 1
    for i, word in enumerate(words):
        value |= (word & mask) << (width * i)
    return value


def make_cases(rows=4, cols=4, batches=12):
    random.seed(41)
    merges = []
    for _ in range(cols):
        merges.append((
            random.uniform(-1.0, 4.0),
            random.uniform(-1.0, 4.0),
            random.uniform(-1.0, 4.0),
        ))

    points = []
    expected_rows = []
    best_idx = 0
    best_dist = np.float32(0.0)
    for b in range(batches):
        batch = []
        for r in range(rows):
            idx = b * rows + r
            x = random.uniform(-2.0, 6.0)
            y = random.uniform(-2.0, 6.0)
            z = random.uniform(-2.0, 6.0)
            in_dist = random.uniform(0.25, 128.0)
            dist = np.float32(in_dist)
            for mx, my, mz in merges:
                d = np.float32(
                    np.float32((x - mx) * (x - mx))
                    + np.float32((y - my) * (y - my))
                    + np.float32((z - mz) * (z - mz))
                )
                dist = np.float32(min(dist, d))
            batch.append((idx, x, y, z, in_dist))
            expected_rows.append({"idx": idx, "dist_bits": f32_bits(dist), "dist": float(dist)})
            if dist > best_dist:
                best_dist = dist
                best_idx = idx
        points.append(batch)
    expected_far = {"idx": best_idx, "dist_bits": f32_bits(best_dist), "dist": float(best_dist)}
    return merges, points, expected_rows, expected_far


def emit_tb(path, gate=False):
    rows, cols, lidx_w = 4, 4, 11
    merges, points, expected_rows, expected_far = make_cases(rows, cols)
    clk = "0.5" if gate else "5"
    mod = "tb_point_engine_gate" if gate else "tb_point_engine_auto"
    dump = ""
    if gate:
        dump = """
    initial begin
        $dumpfile("activity_1ghz/point_engine_gate.vcd");
        $dumpvars(0, tb_point_engine_gate.dut);
    end
"""

    load_blocks = []
    for c, (mx, my, mz) in enumerate(merges):
        mx_words = [0] * cols
        my_words = [0] * cols
        mz_words = [0] * cols
        mx_words[c] = f32_bits(mx)
        my_words[c] = f32_bits(my)
        mz_words[c] = f32_bits(mz)
        load_blocks.append(f"""
        m_x <= 128'h{pack_words(mx_words):032x};
        m_y <= 128'h{pack_words(my_words):032x};
        m_z <= 128'h{pack_words(mz_words):032x};
        m_load <= 4'b{(1 << c):04b};
        @(posedge clk);
""")

    drive_blocks = []
    for batch in points:
        idx_words = [p[0] for p in batch]
        x_words = [f32_bits(p[1]) for p in batch]
        y_words = [f32_bits(p[2]) for p in batch]
        z_words = [f32_bits(p[3]) for p in batch]
        d_words = [f32_bits(p[4]) for p in batch]
        drive_blocks.append(f"""
        in_valid <= 4'b1111;
        in_idx   <= 44'h{pack_idx(idx_words, lidx_w):011x};
        in_x     <= 128'h{pack_words(x_words):032x};
        in_y     <= 128'h{pack_words(y_words):032x};
        in_z     <= 128'h{pack_words(z_words):032x};
        in_dist  <= 128'h{pack_words(d_words):032x};
        @(posedge clk);
""")

    tb = f"""`timescale 1ns/1ps
module {mod};
    reg clk = 0; always #{clk} clk = ~clk;
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
{dump}
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
{''.join(load_blocks)}
        m_load <= 4'b0000;
{''.join(drive_blocks)}
        in_valid <= 4'b0000;
        repeat (96) @(posedge clk);
        $finish;
    end
endmodule
"""
    normalized_tb = "\n".join(line.rstrip() for line in tb.splitlines()) + "\n"
    path.write_text(normalized_tb)
    return {
        "rows": rows,
        "cols": cols,
        "batches": len(points),
        "row_outputs": expected_rows,
        "far": expected_far,
        "merges": [{"x": m[0], "y": m[1], "z": m[2]} for m in merges],
    }


def main():
    TB.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    ref = emit_tb(TB / "tb_point_engine_auto.v", gate=False)
    emit_tb(TB / "tb_point_engine_gate.v", gate=True)
    (REPORTS / "point_engine_tb_reference.json").write_text(json.dumps(ref, indent=2))
    print(REPORTS / "point_engine_tb_reference.json")


if __name__ == "__main__":
    main()
