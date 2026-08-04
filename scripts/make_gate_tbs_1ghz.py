#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
tb_dir = root / "tb"

def convert(src_name, top, extra_finish=20):
    src = (tb_dir / src_name).read_text()
    src = src.replace(f"module tb_{top}_auto;", f"module tb_{top}_gate;")
    src = src.replace("reg clk = 0; always #5 clk = ~clk;", "reg clk = 0; always #0.5 clk = ~clk;")
    src = src.replace("module tb_pe_auto;", "module tb_pe_gate;")
    src = src.replace("module tb_bucket_cd_auto;", "module tb_bucket_cd_gate;")
    src = src.replace("module tb_fp32_ops_auto;", "module tb_fp32_ops_gate;")
    dump = f'''initial begin
        $dumpfile("activity_1ghz/{top}_gate.vcd");
        $dumpvars(0, tb_{top}_gate.dut);
    end
'''
    insert_at = src.find("initial begin")
    src = src[:insert_at] + dump + src[insert_at:]
    (tb_dir / f"tb_{top}_gate.v").write_text(src)

def convert_strict(src_name, source_module, gate_module, top):
    src = (tb_dir / src_name).read_text()
    src = src.replace(f"module {source_module};", f"module {gate_module};")
    src = src.replace("always #5 clk = ~clk;", "always #0.5 clk = ~clk;")
    src = src.replace(f"{source_module}.dut", f"{gate_module}.dut")
    src = re.sub(
        rf"\b{re.escape(top)}\s*#\s*\(.*?\)\s+dut\s*\(",
        f"{top} dut (",
        src,
        flags=re.DOTALL,
    )
    dump = f'''initial begin
        $dumpfile("activity_1ghz/{top}_gate.vcd");
        $dumpvars(0, {gate_module}.dut);
    end
'''
    insert_at = src.find("initial begin")
    src = src[:insert_at] + dump + src[insert_at:]
    normalized = "\n".join(line.rstrip() for line in src.splitlines()) + "\n"
    (tb_dir / f"tb_{top}_gate.v").write_text(normalized)

convert("tb_pe_auto.v", "pe")
convert("tb_bucket_cd_auto.v", "bucket_cd")

subprocess.run(["python3", str(root / "scripts" / "gen_point_engine_tb.py")], check=True)
convert_strict("tb_point_engine_top_cycle.v", "tb_point_engine_top_cycle",
               "tb_point_engine_top_gate", "point_engine_top")
