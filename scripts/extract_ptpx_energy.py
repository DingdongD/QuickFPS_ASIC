#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

POWER_RE = re.compile(
    r"(?P<label>Total\s+Dynamic\s+Power|Cell\s+Leakage\s+Power)\s*=\s*"
    r"(?P<value>[0-9.eE+-]+)\s*(?P<unit>[numk]?W)",
    re.IGNORECASE,
)

UNIT_TO_W = {
    "nw": 1.0e-9,
    "uw": 1.0e-6,
    "mw": 1.0e-3,
    "w": 1.0,
    "kw": 1.0e3,
}


def parse_report(path: Path) -> Tuple[float, float]:
    dynamic_w = None
    leakage_w = None
    for match in POWER_RE.finditer(path.read_text(errors="replace")):
        value_w = float(match.group("value")) * UNIT_TO_W[match.group("unit").lower()]
        label = match.group("label").lower()
        if "dynamic" in label:
            dynamic_w = value_w
        elif "leakage" in label:
            leakage_w = value_w
    if dynamic_w is None:
        raise ValueError(f"could not find Total Dynamic Power in {path}")
    if leakage_w is None:
        leakage_w = 0.0
    return dynamic_w, leakage_w


def counter_list(spec: Dict[str, Any]) -> List[str]:
    raw = spec.get("counters", spec.get("counter", []))
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    raise ValueError(f"invalid PTPX counter mapping: {raw!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("build/ptpx"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--clock-hz", type=float, default=1.0e9)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("modules", nargs="+")
    args = parser.parse_args()

    specs: Dict[str, Any] = {}
    if args.manifest:
        specs = json.loads(args.manifest.read_text()).get("modules", {})

    modules: Dict[str, Dict[str, Any]] = {}
    for module in args.modules:
        report = args.root / module / "reports_ptpx" / "power_summary.rpt"
        dynamic_w, leakage_w = parse_report(report)
        spec = specs.get(module, {})
        modules[module] = {
            "active_pj_per_cycle": dynamic_w / args.clock_hz * 1.0e12,
            "idle_pj_per_cycle": leakage_w / args.clock_hz * 1.0e12,
            "event_pj": float(spec.get("event_pj", 0.0)),
            "counters": counter_list(spec) if spec else [],
            "counter_mode": spec.get("counter_mode", "cycle"),
            "source_dynamic_w": dynamic_w,
            "source_leakage_w": leakage_w,
            "source_report": str(report),
            "note": spec.get("note", ""),
        }

    output = {
        "clock_hz": args.clock_hz,
        "modules": modules,
        "note": (
            "active_pj_per_cycle is VCD-averaged dynamic energy at the "
            "characterization clock; counters select active cycle windows"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
