from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "collect_strict_cycle_ppa", ROOT / "scripts" / "collect_strict_cycle_ppa.py"
)
assert SPEC is not None and SPEC.loader is not None
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


def test_parse_explicit_vcd_window_marker() -> None:
    text = "QUICKFPS_VCD_WINDOW start_ns=5.0 end_ns=74.500000\n"
    assert COLLECTOR.parse_vcd_window(text) == (5.0, 74.5)


def test_parse_vcd_window_from_primetime_echo() -> None:
    text = """\
set VCD_START_NS [getenv VCD_START_NS]
3.0
set VCD_END_NS [getenv VCD_END_NS]
43.500000
"""
    assert COLLECTOR.parse_vcd_window(text) == (3.0, 43.5)


def test_timing_slack_retains_small_violation(tmp_path: Path) -> None:
    report = tmp_path / "setup.rpt"
    report.write_text("slack (VIOLATED) -0.001176\n")
    assert COLLECTOR.timing_slack(report) == -0.001176
