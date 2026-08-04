#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


PTOP_ACCEPT = re.compile(r"PTOP_ACCEPT\s+(\d+)")
PTOP_PUSH = re.compile(r"PTOP_PUSH\s+(\d+)\s+LATENCY\s+(\d+)")
BPIPE_ACCEPT = re.compile(r"BPIPE_ACCEPT\s+(\d+)\s+(\d+)")
BPIPE_OUTPUT = re.compile(r"BPIPE_OUTPUT\s+(\d+)\s+(\d+)")
CORE_SEQUENCE = re.compile(r"CORE_E2E_PASS\s+sequence=([0-9,]+)")
STREAM_PASS = re.compile(
    r"STREAM_SUBSYSTEM_PASS\s+cycles=(\d+)\s+c=(\d+)\s+d=(\d+)\s+w=(\d+)"
)
QTRACE = re.compile(r"^QTRACE\s+(.*)$", re.MULTILINE)


def text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(errors="replace")


def load_reorder_map(path: Path) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for line in text(path).splitlines():
        if not line.strip():
            continue
        reordered, original = (int(value) for value in line.split())
        if reordered in mapping:
            raise AssertionError(f"duplicate reordered index {reordered}")
        mapping[reordered] = original
    if not mapping:
        raise AssertionError("reorder map is empty")
    return mapping


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


def parse_qtrace(content: str) -> List[Dict[str, str]]:
    events = []
    for match in QTRACE.finditer(content):
        fields: Dict[str, str] = {}
        for token in match.group(1).split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            fields[key] = value
        if "cycle" not in fields or "event" not in fields:
            raise AssertionError(f"malformed QTRACE line: {match.group(0)}")
        events.append(fields)
    return events


def validate_pingpong_trace(log_dir: Path) -> Dict[str, object]:
    content = text(log_dir / "tb_pingpong_chunk_ctrl.log")
    events = parse_qtrace(content)
    by_event: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for event in events:
        if event.get("component") == "pingpong":
            by_event[event["event"]].append(event)
    required = [
        "coord_cmd",
        "coord_done",
        "dist_read_cmd",
        "dist_read_done",
        "compute_start",
        "compute_done",
        "dist_write_cmd",
        "dist_write_done",
    ]
    for name in required:
        chunks = [int(event["chunk"]) for event in by_event[name]]
        if chunks != [0, 1, 2]:
            raise AssertionError(f"ping-pong {name} chunks are {chunks}, expected [0,1,2]")
    slots = [int(event["slot"]) for event in by_event["compute_start"]]
    if slots != [0, 1, 0]:
        raise AssertionError(f"ping-pong slot order changed: {slots}")

    cycle_by_event = {
        name: {int(event["chunk"]): int(event["cycle"]) for event in by_event[name]}
        for name in required
    }
    for chunk in range(3):
        read_complete = max(
            cycle_by_event["coord_done"][chunk],
            cycle_by_event["dist_read_done"][chunk],
        )
        compute_start = cycle_by_event["compute_start"][chunk]
        compute_done = cycle_by_event["compute_done"][chunk]
        write_start = cycle_by_event["dist_write_cmd"][chunk]
        write_done = cycle_by_event["dist_write_done"][chunk]
        if compute_start <= read_complete:
            raise AssertionError(f"chunk {chunk} compute started before both reads completed")
        if compute_done <= compute_start:
            raise AssertionError(f"chunk {chunk} compute completion is not causal")
        if write_start <= compute_done:
            raise AssertionError(f"chunk {chunk} write started before compute completion")
        if write_done <= write_start:
            raise AssertionError(f"chunk {chunk} write completion is not causal")

    bucket_done = by_event.get("bucket_done", [])
    if len(bucket_done) != 1:
        raise AssertionError("expected one ping-pong bucket_done event")
    done_cycle = int(bucket_done[0]["cycle"])
    if done_cycle <= max(cycle_by_event["dist_write_done"].values()):
        raise AssertionError("bucket completed before the final MDT write response")
    return {
        "chunks": 3,
        "slot_order": slots,
        "bucket_done_cycle": done_cycle,
        "events": len(events),
    }


def rtl_functional_sequence(log_dir: Path) -> List[int]:
    content = text(log_dir / "tb_quickfps_core_end2end.log")
    match = CORE_SEQUENCE.search(content)
    if not match:
        raise AssertionError("full-core RTL sequence marker is missing")
    return [int(value) for value in match.group(1).split(",")]


def validate_sequence_domains(
    log_dir: Path,
    workload: Dict[str, object],
    reorder_map_path: Path,
    cycle_result: Dict[str, object],
) -> Dict[str, List[int]]:
    rtl_original = rtl_functional_sequence(log_dir)
    workload_reordered = [
        int(value) for value in workload["metadata"]["expected_sequence"]  # type: ignore[index]
    ]
    reorder_map = load_reorder_map(reorder_map_path)
    try:
        workload_original = [reorder_map[index] for index in workload_reordered]
    except KeyError as error:
        raise AssertionError(f"workload index missing from reorder map: {error.args[0]}") from error

    # The host KD-tree uses nth-element partitioning, so a leaf is contiguous
    # but not sorted. Workload/C-model indices are in this reordered memory
    # domain, while the fixed RTL smoke test reports the original point IDs.
    if rtl_original != workload_original:
        raise AssertionError(
            "mapped workload sequence does not match the original-index RTL "
            f"sequence: workload={workload_original}, rtl={rtl_original}"
        )
    cycle_reordered = [int(value) for value in cycle_result["sampled_indices"]]  # type: ignore[index]
    if cycle_reordered != workload_reordered[:-1]:
        raise AssertionError(
            "C-model iteration sequence diverges from the reordered workload: "
            f"cycle={cycle_reordered}, workload={workload_reordered[:-1]}"
        )
    return {
        "rtl_original_indices": rtl_original,
        "workload_reordered_indices": workload_reordered,
        "workload_original_indices": workload_original,
        "cycle_reordered_indices": cycle_reordered,
    }


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
    parser.add_argument("--reorder-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    workload = json.loads(args.workload.read_text())
    cycle_result = json.loads(args.cycle_result.read_text())
    point = validate_point_engine(args.log_dir)
    bucket = validate_bucket_pipe(args.log_dir)
    pingpong = validate_pingpong_trace(args.log_dir)
    sequences = validate_sequence_domains(
        args.log_dir, workload, args.reorder_map, cycle_result
    )
    stream = validate_stream_subsystem(args.log_dir)

    accelerator = cycle_result["config"]["accelerator"]
    if int(accelerator["bucket_issue_ii"]) != 1:
        raise AssertionError("C-model bucket_issue_ii diverges from RTL II=1 trace")
    row_latency = int(accelerator["pe_cols"]) * int(accelerator["pe_cell_latency"])
    expected_latency = (
        int(accelerator["merge_load_cycles"])
        + 12
        + row_latency
        + int(accelerator["point_ctrl_overhead"])
    )
    if expected_latency != point["latency"]:
        raise AssertionError(
            f"C-model 48-point latency {expected_latency} != RTL {point['latency']}"
        )

    summary = {
        "point_engine": point,
        "bucket_decision_pipe": bucket,
        "pingpong_chunk_ctrl": pingpong,
        "stream_subsystem": stream,
        "sequences": sequences,
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
