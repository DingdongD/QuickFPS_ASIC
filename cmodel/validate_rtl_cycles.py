#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


PTOP_ACCEPT = re.compile(r"PTOP_ACCEPT\s+(\d+)")
PTOP_PUSH = re.compile(r"PTOP_PUSH\s+(\d+)\s+LATENCY\s+(\d+)")
BPIPE_ACCEPT = re.compile(r"BPIPE_ACCEPT\s+(\d+)\s+(\d+)")
BPIPE_OUTPUT = re.compile(r"BPIPE_OUTPUT\s+(\d+)\s+(\d+)")
CORE_SEQUENCE = re.compile(r"CORE_E2E_PASS\s+sequence=([0-9,]+)")
STREAM_PASS = re.compile(
    r"STREAM_SUBSYSTEM_PASS\s+cycles=(\d+)\s+c=(\d+)\s+d=(\d+)\s+w=(\d+)"
)


def text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(errors="replace")


def validate_point_engine(log_dir: Path) -> Dict[str, int]:
    content = text(log_dir / "tb_point_engine_top_cycle.log")
    accepts = [int(value) for value in PTOP_ACCEPT.findall(content)]
    pushes = [(int(cycle), int(latency)) for cycle, latency in PTOP_PUSH.findall(content)]
    if len(accepts) != 1 or len(pushes) != 1:
        raise AssertionError("expected one Point-Engine accept/push pair")
    push_cycle, latency = pushes[0]
    if push_cycle - accepts[0] != latency:
        raise AssertionError("Point-Engine reported latency is inconsistent")
    if latency != 38:
        raise AssertionError(f"validated Point-Engine latency changed: {latency}")
    return {"accept_cycle": accepts[0], "push_cycle": push_cycle, "latency": latency}


def validate_bucket_pipe(log_dir: Path) -> Dict[str, int]:
    content = text(log_dir / "tb_bucket_decision_pipe.log")
    accepts = [(int(cycle), int(index)) for cycle, index in BPIPE_ACCEPT.findall(content)]
    outputs = [(int(cycle), int(index)) for cycle, index in BPIPE_OUTPUT.findall(content)]
    if [index for _, index in accepts] != list(range(16)):
        raise AssertionError("bucket pipeline did not accept the expected ordered sequence")
    if [index for _, index in outputs] != list(range(16)):
        raise AssertionError("bucket pipeline reordered decisions")
    if outputs[0][0] - accepts[0][0] < 4:
        raise AssertionError("bucket decision appeared before the four-stage CD latency")
    # Before the deliberate consumer stall, the source must sustain one accepted
    # bucket per cycle.  This is the RTL calibration for bucket_issue_ii=1.
    consecutive = 1
    for (prev_cycle, _), (cycle, _) in zip(accepts, accepts[1:]):
        if cycle == prev_cycle + 1:
            consecutive += 1
        else:
            break
    if consecutive < 8:
        raise AssertionError(f"bucket II=1 window too short: {consecutive}")
    return {
        "accepted": len(accepts),
        "outputs": len(outputs),
        "first_latency": outputs[0][0] - accepts[0][0],
        "initial_ii1_window": consecutive,
    }


def validate_functional_sequence(log_dir: Path, workload: Dict[str, object]) -> List[int]:
    content = text(log_dir / "tb_quickfps_core_end2end.log")
    match = CORE_SEQUENCE.search(content)
    if not match:
        raise AssertionError("full-core RTL sequence marker is missing")
    rtl_sequence = [int(value) for value in match.group(1).split(",")]
    expected = [int(value) for value in workload["metadata"]["expected_sequence"]]  # type: ignore[index]
    if rtl_sequence != expected:
        raise AssertionError(
            f"RTL sequence {rtl_sequence} does not match workload sequence {expected}"
        )
    return rtl_sequence


def validate_stream_subsystem(log_dir: Path) -> Dict[str, int]:
    content = text(log_dir / "tb_quickfps_stream_subsystem.log")
    match = STREAM_PASS.search(content)
    if not match:
        raise AssertionError("stream subsystem pass marker is missing")
    cycles, coord, dist, write = (int(value) for value in match.groups())
    if min(coord, dist, write) <= 0:
        raise AssertionError("stream subsystem produced no AXI traffic")
    return {
        "cycles": cycles,
        "coordinate_bursts": coord,
        "distance_read_bursts": dist,
        "distance_write_bursts": write,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--cycle-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    workload = json.loads(args.workload.read_text())
    cycle_result = json.loads(args.cycle_result.read_text())
    point = validate_point_engine(args.log_dir)
    bucket = validate_bucket_pipe(args.log_dir)
    sequence = validate_functional_sequence(args.log_dir, workload)
    stream = validate_stream_subsystem(args.log_dir)

    if int(cycle_result["config"]["accelerator"]["bucket_issue_ii"]) != 1:
        raise AssertionError("C-model bucket_issue_ii diverges from RTL II=1 trace")
    expected_latency = int(
        cycle_result["config"]["accelerator"]["merge_load_cycles"]
    ) + 12 + int(cycle_result["config"]["accelerator"]["pe_row_latency"])
    expected_latency += int(
        cycle_result["config"]["accelerator"]["point_ctrl_overhead"]
    )
    if expected_latency != point["latency"]:
        raise AssertionError(
            f"C-model 48-point latency {expected_latency} != RTL {point['latency']}"
        )
    if cycle_result["sampled_indices"] != sequence[:-1]:
        # A timing workload has one iteration per transition, so its sampled
        # list excludes the terminal selected point.
        raise AssertionError("C-model iteration sequence diverges from RTL/workload")

    summary = {
        "point_engine": point,
        "bucket_decision_pipe": bucket,
        "stream_subsystem": stream,
        "rtl_sequence": sequence,
        "cycle_model_cycles": int(cycle_result["cycles"]),
        "cycle_model_iterations": int(cycle_result["iterations"]),
        "status": "pass",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
