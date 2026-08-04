#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def run(command: List[str], env: Dict[str, str], cwd: Path) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run DC, gate-VCD simulation, and PTPX for cycle modules"
    )
    parser.add_argument("--manifest", type=Path, default=Path("ptpx/cycle_modules.json"))
    parser.add_argument("--target-db", type=Path, required=True)
    parser.add_argument("--cell-verilog", type=Path, required=True)
    parser.add_argument("--modules", nargs="*", help="default: all manifest modules")
    parser.add_argument("--dc-shell", default="dc_shell")
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--pt-shell", default="pt_shell")
    parser.add_argument("--output", type=Path, default=Path("build/ptpx_energy.json"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    manifest: Dict[str, Any] = json.loads(manifest_path.read_text())
    available: Dict[str, Any] = manifest["modules"]
    selected = args.modules or list(available)
    unknown = [name for name in selected if name not in available]
    if unknown:
        raise SystemExit(f"unknown PTPX modules: {', '.join(unknown)}")

    target_db = args.target_db.resolve()
    cell_verilog = args.cell_verilog.resolve()
    if not target_db.is_file():
        raise SystemExit(f"target library not found: {target_db}")
    if not cell_verilog.is_file():
        raise SystemExit(f"cell Verilog not found: {cell_verilog}")

    completed = []
    for name in selected:
        spec = available[name]
        vcd = root / spec["vcd"]
        env = dict(os.environ)
        env.update(
            {
                "WORK_ROOT": str(root),
                "TOP_NAME": name,
                "TB_FILE": spec["testbench"],
                "TB_TOP": spec["testbench_top"],
                "STRIP_PATH": spec["strip_path"],
                "VCD_FILE": str(vcd),
                "TARGET_DB": str(target_db),
                "CELL_VERILOG": str(cell_verilog),
                "CLOCK_PERIOD_NS": str(manifest.get("clock_period_ns", 1.0)),
                "DC_SHELL": args.dc_shell,
                "VCS": args.vcs,
                "PT_SHELL": args.pt_shell,
            }
        )
        run(["bash", "scripts/run_cycle_ptpx.sh"], env=env, cwd=root)
        report = root / "build" / "ptpx" / name / "reports_ptpx" / "power_summary.rpt"
        if not report.is_file():
            raise RuntimeError(f"PTPX report missing for {name}: {report}")
        completed.append(name)

    output = args.output if args.output.is_absolute() else root / args.output
    run(
        [
            "python3",
            "scripts/extract_ptpx_energy.py",
            "--root",
            "build/ptpx",
            "--manifest",
            str(manifest_path),
            "--clock-hz",
            str(1.0e9 / float(manifest.get("clock_period_ns", 1.0))),
            "--output",
            str(output),
            *completed,
        ],
        env=dict(os.environ),
        cwd=root,
    )
    print(f"PTPX_MANIFEST_PASS modules={','.join(completed)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
