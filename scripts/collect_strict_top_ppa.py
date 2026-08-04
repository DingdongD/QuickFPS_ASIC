#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

import yaml


TOPS = ("point_engine_top", "bucket_engine")
FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TIMING_TOLERANCE_NS = 1.0e-6
ALLOWED_PTPX_ERRORS = ("Error: Library Compiler executable path is not set. (PT-063)",)


def read(path: Path) -> str:
    return path.read_text(errors="ignore")


def match_float(text: str, pattern: str):
    match = re.search(pattern, text, re.MULTILINE)
    return float(match.group(1)) if match else None


def match_int(text: str, pattern: str):
    match = re.search(pattern, text, re.MULTILINE)
    return int(match.group(1)) if match else None


def timing_slack(path: Path):
    value = match_float(
        read(path), rf"slack\s+\((?:MET|VIOLATED[^)]*)\)\s+({FLOAT})"
    )
    return value


def constraint_violations(path: Path):
    text = read(path)
    headings = list(
        re.finditer(r"^\s+((?:min|max)_[a-z_]+)\s*$", text, re.MULTILINE)
    )
    violations = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end():end]
        if "(VIOLATED)" in section and heading.group(1) != "max_leakage_power":
            violations.append(heading.group(1))
    return violations


def analysis_coverage(path: Path, check_type: str):
    match = re.search(
        rf"^{check_type}\s+(\d+)\s+(\d+)\s+\([^)]*\)\s+"
        rf"(\d+)\s+\([^)]*\)\s+(\d+)\s+\([^)]*\)",
        read(path),
        re.MULTILINE,
    )
    if not match:
        return None
    return {
        "total": int(match.group(1)),
        "met": int(match.group(2)),
        "violated": int(match.group(3)),
        "untested": int(match.group(4)),
    }


def collect_top(root: Path, top: str, min_leaf_pct: float):
    dc_dir = root / "reports_1ghz" / top
    pt_dir = root / "reports_1ghz" / f"{top}_ptpx_vcd"
    log = root / "logs" / f"ptpx_1ghz_vcd_{top}.log"
    golden_path = root / "golden_1ghz" / f"{top}_gate_golden.json"
    required = [
        dc_dir / "area.rpt",
        dc_dir / "timing_setup.rpt",
        dc_dir / "timing_hold.rpt",
        dc_dir / "constraints.rpt",
        pt_dir / "power_ptpx_vcd.rpt",
        pt_dir / "timing_setup.rpt",
        pt_dir / "timing_hold.rpt",
        pt_dir / "constraints.rpt",
        pt_dir / "analysis_coverage.rpt",
        log,
        golden_path,
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        return None, {"reason": "missing required strict artifacts", "missing": missing}

    golden_doc = json.loads(golden_path.read_text())
    golden = golden_doc.get(top, {})
    area_text = read(dc_dir / "area.rpt")
    power_text = read(pt_dir / "power_ptpx_vcd.rpt")
    log_text = read(log)

    total_nets = match_int(log_text, r"Total number of nets\s*=\s*(\d+)")
    annotated_nets = match_int(log_text, r"Number of annotated nets\s*=\s*(\d+)")
    total_leaf = match_int(log_text, r"Total number of leaf cells\s*=\s*(\d+)")
    annotated_leaf = match_int(
        log_text, r"Number of fully annotated leaf cells\s*=\s*(\d+)"
    )
    invariant = re.search(
        r"Total number of synthesis invariant points\s*=\s*(\d+)\s*,\s*"
        r"annotated synthesis invariant points\s*=\s*(\d+)",
        log_text,
    )
    total_invariant = int(invariant.group(1)) if invariant else None
    annotated_invariant = int(invariant.group(2)) if invariant else None
    net_pct = 100.0 * annotated_nets / total_nets if total_nets else None
    leaf_pct = 100.0 * annotated_leaf / total_leaf if total_leaf else None

    power = re.search(
        rf"^{re.escape(top)}\s+({FLOAT})\s+({FLOAT})\s+({FLOAT})\s+({FLOAT})\s+",
        power_text,
        re.MULTILINE,
    )
    dc_setup = timing_slack(dc_dir / "timing_setup.rpt")
    dc_hold = timing_slack(dc_dir / "timing_hold.rpt")
    pt_setup = timing_slack(pt_dir / "timing_setup.rpt")
    pt_hold = timing_slack(pt_dir / "timing_hold.rpt")
    violations = sorted(set(
        constraint_violations(dc_dir / "constraints.rpt")
        + constraint_violations(pt_dir / "constraints.rpt")
    ))
    setup_coverage = analysis_coverage(pt_dir / "analysis_coverage.rpt", "setup")
    hold_coverage = analysis_coverage(pt_dir / "analysis_coverage.rpt", "hold")
    ptpx_errors = [
        line.strip() for line in log_text.splitlines()
        if line.startswith("Error:") and line.strip() not in ALLOWED_PTPX_ERRORS
    ]

    checks = {
        "gate_level_golden_pass": golden.get("pass") is True,
        "all_nets_from_gate_vcd": total_nets is not None and total_nets == annotated_nets,
        "all_synthesis_invariants_annotated": total_invariant is not None
        and total_invariant == annotated_invariant,
        "leaf_annotation_meets_threshold": leaf_pct is not None and leaf_pct >= min_leaf_pct,
        "dc_setup_hold_clean": None not in (dc_setup, dc_hold)
        and dc_setup >= -TIMING_TOLERANCE_NS and dc_hold >= -TIMING_TOLERANCE_NS,
        "ptpx_setup_hold_clean": None not in (pt_setup, pt_hold)
        and pt_setup >= -TIMING_TOLERANCE_NS and pt_hold >= -TIMING_TOLERANCE_NS,
        "no_physical_constraint_violations": not violations,
        "power_report_present": power is not None,
        "setup_hold_coverage_has_no_violations": setup_coverage is not None
        and hold_coverage is not None
        and setup_coverage["violated"] == 0
        and hold_coverage["violated"] == 0,
        "no_fatal_ptpx_errors": not ptpx_errors,
    }
    if not all(checks.values()):
        return None, {
            "reason": "strict acceptance failed",
            "checks": checks,
            "gate_level_golden": golden,
            "net_annotation_pct": net_pct,
            "fully_annotated_leaf_cells_pct": leaf_pct,
            "constraint_violations": violations,
            "fatal_ptpx_errors": ptpx_errors,
        }

    values = [float(power.group(index)) for index in range(1, 5)]
    cycle_model = {
        key: golden[key]
        for key in ("latency_cycles", "requests", "responses")
        if key in golden
    }
    return {
        "gate_level_golden": golden,
        "dc_1ghz": {
            "cell_area": match_float(area_text, rf"Total cell area:\s+({FLOAT})"),
            "comb_area": match_float(area_text, rf"Combinational area:\s+({FLOAT})"),
            "seq_area": match_float(area_text, rf"Noncombinational area:\s+({FLOAT})"),
            "cells": match_int(area_text, r"Number of cells:\s+(\d+)"),
            "setup_slack_ns": dc_setup,
            "hold_slack_ns": dc_hold,
            "physical_constraint_violations": violations,
        },
        "gate_vcd_annotation": {
            "annotated_nets": annotated_nets,
            "total_nets": total_nets,
            "nets_from_vcd_pct": round(net_pct, 6),
            "fully_annotated_leaf_cells": annotated_leaf,
            "total_leaf_cells": total_leaf,
            "fully_annotated_leaf_cells_pct": round(leaf_pct, 6),
            "minimum_leaf_cells_pct": min_leaf_pct,
            "annotated_synthesis_invariant_points": annotated_invariant,
            "total_synthesis_invariant_points": total_invariant,
        },
        "ptpx_analysis_coverage": {
            "setup": setup_coverage,
            "hold": hold_coverage,
        },
        "ptpx_gate_vcd_power_w": {
            "internal": values[0],
            "switching": values[1],
            "leakage": values[2],
            "total": values[3],
        },
        "ptpx_timing": {
            "setup_slack_ns": pt_setup,
            "hold_slack_ns": pt_hold,
        },
        "cycle_model": cycle_model,
        "strict_acceptance": checks,
    }, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--min-leaf-pct", type=float, default=99.8)
    args = parser.parse_args()

    modules = {}
    excluded = {}
    for top in TOPS:
        result, error = collect_top(args.result_root, top, args.min_leaf_pct)
        if result is not None:
            modules[top] = result
        else:
            excluded[top] = error

    document = {
        "run": {
            "result_root": str(args.result_root),
            "process": "TSMC28 HPC+ BWP40P140 SSG 0.81V 125C",
            "clock_period_ns": 1.0,
            "flow": "DC mapped netlist -> gate-level VCS/VCD -> PTPX read_vcd/update_power",
            "strict_policy": {
                "gate_golden_required": True,
                "net_vcd_annotation_pct": 100.0,
                "minimum_fully_annotated_leaf_cells_pct": args.min_leaf_pct,
                "setup_hold_and_physical_constraints_clean": True,
                "timing_numeric_tolerance_ns": TIMING_TOLERANCE_NS,
                "allowed_nonfatal_ptpx_messages": list(ALLOWED_PTPX_ERRORS),
            },
        },
        "strict_gate_vcd_ppa": modules,
        "excluded": excluded,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(document, sort_keys=False))
    print(args.output)
    if excluded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
