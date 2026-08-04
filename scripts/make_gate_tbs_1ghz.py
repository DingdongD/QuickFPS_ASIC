#!/usr/bin/env python3
from pathlib import Path
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

convert("tb_pe_auto.v", "pe")
convert("tb_bucket_cd_auto.v", "bucket_cd")

subprocess.run(["python3", str(root / "scripts" / "gen_point_engine_tb.py")], check=True)
