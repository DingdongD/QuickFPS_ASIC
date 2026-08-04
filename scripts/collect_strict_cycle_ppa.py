#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TIMING_TOLERANCE_NS = 1.0e-6
ALLOWED_PTPX_ERRORS = (
    "Error: Library Compiler executable path is not set. (PT-063)",
)


def read(path: Path) -> str:
    return path.read_text(errors="replace")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def match_float(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.MULTILINE)
    return float(match.group(1)) if match else None


def match_int(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.MULTILINE)
    return int(match.group(1)) if match else None


def timing_slack(path: Path) -> float | None:
    return match_float(
        read(path), rf"slack\s+\((?:MET|VIOLATED[^)]*)\)\s+({FLOAT})"
    )


def constraint_violations(path: Path) -> list[str]:
    text = read(path)
    headings = list(
        re.finditer(r"^\s+((?:min|max)_[a-z_]+)\s*$", text, re.MULTILINE)
    )
    violations: list[str] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end() : end]
        if "(VIOLATED)" in section and heading.group(1) != "max_leakage_power":
            violations.append(heading.group(1))
    return violations


def analysis_coverage(path: Path, check_type: str) -> dict[str, int] | None:
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


def parse_power(path: Path, top: str) -> dict[str, float] | None:
    match = re.search(
        rf"^{re.escape(top)}\s+({FLOAT})\s+({FLOAT})\s+({FLOAT})\s+({FLOAT})\s+",
        read(path),
        re.MULTILINE,
    )
    if not match:
        return None
    values = [float(match.group(index)) for index in range(1, 5)]
    return dict(zip(("internal", "switching", "leakage", "total"), values))


def parse_gate_metrics(text: str) -> dict[str, int]:
    metrics = {
        key: int(value)
        for key, value in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(\d+)\b", text)
    }
    latency = re.search(r"\bLATENCY\s+(\d+)\b", text)
    if latency:
        metrics["latency_cycles"] = int(latency.group(1))
    return metrics


def parse_vcd_window(text: str) -> tuple[float | None, float | None]:
    marker = re.search(
        rf"QUICKFPS_VCD_WINDOW\s+start_ns=({FLOAT})\s+end_ns=({FLOAT})",
        text,
    )
    if marker:
        return float(marker.group(1)), float(marker.group(2))

    # PrimeTime echoes Tcl commands and their return values. Runs produced
    # before the explicit marker above can therefore still be audited without
    # re-running power analysis or trusting the collector's command line.
    start = re.search(
        rf"^set VCD_START_NS \[getenv VCD_START_NS\]\s*$\n({FLOAT})\s*$",
        text,
        re.MULTILINE,
    )
    end = re.search(
        rf"^set VCD_END_NS \[getenv VCD_END_NS\]\s*$\n({FLOAT})\s*$",
        text,
        re.MULTILINE,
    )
    return (
        float(start.group(1)) if start else None,
        float(end.group(1)) if end else None,
    )


def parse_check_design(path: Path) -> dict[str, int]:
    text = read(path)
    lint_counts: dict[str, int] = {}
    for description, code, count in re.findall(
        r"^\s{4}(.+?)\s+\((LINT-\d+)\)\s+(\d+)\s*$", text, re.MULTILINE
    ):
        del description
        lint_counts[code] = lint_counts.get(code, 0) + int(count)
    return lint_counts


def collect_module(
    root: Path,
    source_root: Path,
    module: str,
    spec: dict[str, Any],
    clock_hz: float,
    min_leaf_pct: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    base = root / "build" / "ptpx" / module
    dc = base / "reports_dc"
    pt = base / "reports_ptpx"
    gate_log = base / "gate_sim" / "gate_sim.log"
    pt_log = base / "ptpx.log"
    vcd = root / spec["vcd"]
    required = [
        dc / "area.rpt",
        dc / "check_design.rpt",
        dc / "setup.rpt",
        dc / "hold.rpt",
        dc / "constraints.rpt",
        pt / "power.rpt",
        pt / "setup.rpt",
        pt / "hold.rpt",
        pt / "constraints.rpt",
        pt / "analysis_coverage.rpt",
        gate_log,
        pt_log,
        vcd,
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        return None, {"reason": "missing strict artifacts", "missing": missing}

    gate_text = read(gate_log)
    pt_text = read(pt_log)
    area_text = read(dc / "area.rpt")
    pass_regex = str(spec.get("gate_pass_regex", "_PASS"))
    gate_pass = re.search(pass_regex, gate_text) is not None

    total_nets = match_int(pt_text, r"Total number of nets\s*=\s*(\d+)")
    annotated_nets = match_int(pt_text, r"Number of annotated nets\s*=\s*(\d+)")
    total_leaf = match_int(pt_text, r"Total number of leaf cells\s*=\s*(\d+)")
    annotated_leaf = match_int(
        pt_text, r"Number of fully annotated leaf cells\s*=\s*(\d+)"
    )
    invariant = re.search(
        r"Total number of synthesis invariant points\s*=\s*(\d+)\s*,\s*"
        r"annotated synthesis invariant points\s*=\s*(\d+)",
        pt_text,
    )
    total_invariant = int(invariant.group(1)) if invariant else None
    annotated_invariant = int(invariant.group(2)) if invariant else None
    net_pct = 100.0 * annotated_nets / total_nets if total_nets else None
    leaf_pct = 100.0 * annotated_leaf / total_leaf if total_leaf else None
    vcd_start_ns, vcd_end_ns = parse_vcd_window(pt_text)
    vcd_duration_ns = (
        vcd_end_ns - vcd_start_ns
        if vcd_start_ns is not None and vcd_end_ns is not None
        else None
    )
    expected_start_ns = float(spec.get("vcd_start_ns", 0.0))

    dc_setup = timing_slack(dc / "setup.rpt")
    dc_hold = timing_slack(dc / "hold.rpt")
    pt_setup = timing_slack(pt / "setup.rpt")
    pt_hold = timing_slack(pt / "hold.rpt")
    violations = sorted(
        set(
            constraint_violations(dc / "constraints.rpt")
            + constraint_violations(pt / "constraints.rpt")
        )
    )
    setup_coverage = analysis_coverage(pt / "analysis_coverage.rpt", "setup")
    hold_coverage = analysis_coverage(pt / "analysis_coverage.rpt", "hold")
    power = parse_power(pt / "power.rpt", module)
    fatal_pt_errors = [
        line.strip()
        for line in pt_text.splitlines()
        if line.startswith("Error:") and line.strip() not in ALLOWED_PTPX_ERRORS
    ]
    gate_timing_violations = len(
        re.findall(r"Timing violation", gate_text, re.IGNORECASE)
    )

    checks = {
        "gate_level_golden_pass": gate_pass,
        "gate_level_timing_clean": gate_timing_violations == 0,
        "all_nets_from_gate_vcd": total_nets is not None
        and total_nets == annotated_nets,
        "all_synthesis_invariants_annotated": total_invariant is not None
        and total_invariant == annotated_invariant,
        "active_vcd_window_applied": vcd_start_ns is not None
        and abs(vcd_start_ns - expected_start_ns) <= TIMING_TOLERANCE_NS
        and vcd_duration_ns is not None
        and vcd_duration_ns > 0.0,
        "leaf_annotation_meets_threshold": leaf_pct is not None
        and leaf_pct >= min_leaf_pct,
        "dc_setup_hold_clean": None not in (dc_setup, dc_hold)
        and dc_setup >= -TIMING_TOLERANCE_NS
        and dc_hold >= -TIMING_TOLERANCE_NS,
        "ptpx_setup_hold_clean": None not in (pt_setup, pt_hold)
        and pt_setup >= -TIMING_TOLERANCE_NS
        and pt_hold >= -TIMING_TOLERANCE_NS,
        "no_physical_constraint_violations": not violations,
        "power_report_present": power is not None,
        "analysis_coverage_has_no_violations": setup_coverage is not None
        and hold_coverage is not None
        and setup_coverage["violated"] == 0
        and hold_coverage["violated"] == 0,
        "no_fatal_ptpx_errors": not fatal_pt_errors,
    }
    if not all(checks.values()):
        return None, {
            "reason": "strict acceptance failed",
            "checks": checks,
            "net_annotation_pct": net_pct,
            "fully_annotated_leaf_cells_pct": leaf_pct,
            "constraint_violations": violations,
            "fatal_ptpx_errors": fatal_pt_errors,
            "gate_level_timing_violations": gate_timing_violations,
            "vcd_start_ns": vcd_start_ns,
            "expected_vcd_start_ns": expected_start_ns,
        }

    assert power is not None
    dynamic_w = power["internal"] + power["switching"]
    ppa = {
        "composition_group": spec.get("composition_group", "standalone"),
        "simulator_eligible": bool(spec.get("simulator_eligible", True)),
        "counters": list(spec.get("counters", [])),
        "instances": int(spec.get("instances", 1)),
        "gate_level_workload": parse_gate_metrics(gate_text),
        "dc_1ghz": {
            "cell_area": match_float(area_text, rf"Total cell area:\s+({FLOAT})"),
            "comb_area": match_float(area_text, rf"Combinational area:\s+({FLOAT})"),
            "seq_area": match_float(
                area_text, rf"Noncombinational area:\s+({FLOAT})"
            ),
            "cells": match_int(area_text, r"Number of cells:\s+(\d+)"),
            "setup_slack_ns": dc_setup,
            "hold_slack_ns": dc_hold,
            "check_design_lint_counts": parse_check_design(
                dc / "check_design.rpt"
            ),
        },
        "gate_vcd": {
            "path": str(vcd.relative_to(root)),
            "sha256": sha256(vcd),
            "annotated_nets": annotated_nets,
            "total_nets": total_nets,
            "nets_from_vcd_pct": round(net_pct, 6),
            "fully_annotated_leaf_cells": annotated_leaf,
            "total_leaf_cells": total_leaf,
            "fully_annotated_leaf_cells_pct": round(leaf_pct, 6),
            "minimum_leaf_cells_pct": min_leaf_pct,
            "timing_violations": gate_timing_violations,
            "analysis_start_ns": vcd_start_ns,
            "analysis_end_ns": vcd_end_ns,
            "analysis_duration_ns": vcd_duration_ns,
            "annotated_synthesis_invariant_points": annotated_invariant,
            "total_synthesis_invariant_points": total_invariant,
        },
        "testbench": {
            "path": spec["testbench"],
            "sha256": sha256(source_root / spec["testbench"]),
            "pass_regex": pass_regex,
        },
        "ptpx_analysis_coverage": {"setup": setup_coverage, "hold": hold_coverage},
        "ptpx_gate_vcd_power_w": power,
        "ptpx_timing": {"setup_slack_ns": pt_setup, "hold_slack_ns": pt_hold},
        "energy_model": {
            "active_total_pj_per_cycle": power["total"] / clock_hz * 1.0e12,
            "active_dynamic_pj_per_cycle": dynamic_w / clock_hz * 1.0e12,
            "inactive_leakage_pj_per_cycle": power["leakage"]
            / clock_hz
            * 1.0e12,
            "characterization": "workload-averaged gate-VCD dynamic power",
            "idle_model": "leakage-only lower bound; no dedicated idle VCD",
        },
        "strict_acceptance": checks,
    }
    return ppa, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    parser.add_argument("output_yaml", type=Path)
    parser.add_argument("output_energy_json", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("ptpx/cycle_modules.json"))
    parser.add_argument("--modules", nargs="*")
    parser.add_argument("--min-leaf-pct", type=float, default=99.8)
    parser.add_argument("--cycle-validation", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()

    manifest_path = (
        args.manifest
        if args.manifest.is_absolute()
        else args.result_root / args.manifest
    )
    manifest = json.loads(manifest_path.read_text())
    specs = manifest["modules"]
    modules = args.modules or list(specs)
    clock_hz = 1.0e9 / float(manifest.get("clock_period_ns", 1.0))
    source_root = args.source_root or args.result_root

    accepted: dict[str, Any] = {}
    excluded: dict[str, Any] = {}
    energy_modules: dict[str, Any] = {}
    for module in modules:
        if module not in specs:
            raise SystemExit(f"unknown manifest module: {module}")
        result, error = collect_module(
            args.result_root,
            source_root,
            module,
            specs[module],
            clock_hz,
            args.min_leaf_pct,
        )
        if result is None:
            excluded[module] = error
            continue
        accepted[module] = result
        if result["simulator_eligible"] and bool(
            specs[module].get("default_characterize", True)
        ):
            energy = result["energy_model"]
            energy_modules[module] = {
                "active_pj_per_cycle": energy["active_total_pj_per_cycle"],
                "idle_pj_per_cycle": energy["inactive_leakage_pj_per_cycle"],
                "event_pj": 0.0,
                "counters": result["counters"],
                "counter_mode": "cycle",
                "instances": result["instances"],
                "cell_area": result["dc_1ghz"]["cell_area"],
                "composition_group": result["composition_group"],
                "strict_gate_vcd": True,
                "source_module": module,
            }

    cycle_validation = None
    if args.cycle_validation:
        cycle_validation = json.loads(args.cycle_validation.read_text())
        if cycle_validation.get("status") != "pass":
            raise SystemExit("RTL-to-C-model cycle validation is not passing")

    document = {
        "run": {
            "process": "TSMC28 HPC+ BWP40P140 SSG 0.81V 125C",
            "clock_period_ns": float(manifest.get("clock_period_ns", 1.0)),
            "flow": "DC mapped netlist -> gate-level VCS/SDF/VCD -> PTPX read_vcd/update_power",
            "rtl_tree_sha256": tree_sha256(source_root / "RTL"),
            "strict_policy": {
                "gate_golden_required": True,
                "net_vcd_annotation_pct": 100.0,
                "minimum_fully_annotated_leaf_cells_pct": args.min_leaf_pct,
                "setup_hold_and_constraints_clean": True,
            },
        },
        "strict_gate_vcd_ppa": accepted,
        "rtl_cycle_validation": cycle_validation,
        "excluded": excluded,
    }
    args.output_yaml.parent.mkdir(parents=True, exist_ok=True)
    args.output_yaml.write_text(yaml.safe_dump(document, sort_keys=False))

    energy_document = {
        "schema_version": 2,
        "clock_hz": clock_hz,
        "process": document["run"]["process"],
        "modules": energy_modules,
        "rtl_cycle_validation": cycle_validation,
        "composition_rule": (
            "Do not sum modules from streaming_leaf and streaming_aggregate in "
            "the same estimate. SRAM macro energy is intentionally absent."
        ),
    }
    args.output_energy_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_energy_json.write_text(
        json.dumps(energy_document, indent=2, sort_keys=True) + "\n"
    )
    print(args.output_yaml)
    print(args.output_energy_json)
    if excluded:
        print("excluded=" + ",".join(sorted(excluded)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
