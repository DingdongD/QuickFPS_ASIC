#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Pair:
    strict_path: Path
    event_path: Path
    strict_cycles: float
    event_cycles: float
    base_cycles: float
    memory_exposure: float


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_pair(strict_path: Path, event_path: Path) -> Pair:
    strict = load_json(strict_path)
    event = load_json(event_path)
    if strict.get("mode") not in {"closed-loop", "trace-replay"}:
        raise ValueError(f"{strict_path}: not a strict simulator result")
    if event.get("mode") != "closed-loop-event":
        raise ValueError(f"{event_path}: not an event-model result")
    if strict.get("sampled_indices") != event.get("sampled_indices"):
        raise ValueError(
            f"functional mismatch for {strict_path} and {event_path}"
        )
    strict_cycles = float(strict["cycles"])
    event_cycles = float(event["cycles"])
    counters = event.get("counters", {})
    bucket = float(counters.get("bucket_scan_cycles", 0.0))
    compute = float(counters.get("point_compute_cycles", 0.0))
    # Bucket scanning and Point-Engine execution overlap.  Their maximum is a
    # conservative non-memory floor; the residual is the exposed memory and
    # controller contribution that the calibration scales.
    base = min(event_cycles, max(bucket, compute, 1.0))
    exposure = max(1.0, event_cycles - base)
    return Pair(
        strict_path,
        event_path,
        strict_cycles,
        event_cycles,
        base,
        exposure,
    )


def predict(pair: Pair, scale: float) -> float:
    return pair.base_cycles + pair.memory_exposure * scale


def error_pct(pair: Pair, scale: float) -> float:
    return abs(predict(pair, scale) - pair.strict_cycles) / pair.strict_cycles * 100.0


def fit_scale(pairs: Iterable[Pair]) -> float:
    values = list(pairs)
    numerator = 0.0
    denominator = 0.0
    for pair in values:
        target = max(0.0, pair.strict_cycles - pair.base_cycles)
        numerator += pair.memory_exposure * target
        denominator += pair.memory_exposure * pair.memory_exposure
    if denominator <= 0.0:
        raise ValueError("calibration pairs contain no memory exposure")
    return min(8.0, max(0.125, numerator / denominator))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "Fit the event-driven DRAM latency scale from matched strict "
            "DRAMsim3 and full-workload event-model results"
        )
    )
    value.add_argument(
        "--pair",
        nargs=2,
        action="append",
        metavar=("STRICT_JSON", "EVENT_JSON"),
        required=True,
    )
    value.add_argument(
        "--holdout",
        type=int,
        default=0,
        help="reserve the final N pairs for held-out error reporting",
    )
    value.add_argument("--read-to-write-turnaround", type=int, default=4)
    value.add_argument("--write-to-read-turnaround", type=int, default=4)
    value.add_argument("--output", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    pairs = [load_pair(Path(strict), Path(event)) for strict, event in args.pair]
    if args.holdout < 0 or args.holdout >= len(pairs):
        if args.holdout != 0:
            raise SystemExit("--holdout must be smaller than the pair count")
    train = pairs[:-args.holdout] if args.holdout else pairs
    holdout = pairs[-args.holdout:] if args.holdout else []
    scale = fit_scale(train)
    train_errors = [error_pct(pair, scale) for pair in train]
    holdout_errors = [error_pct(pair, scale) for pair in holdout]
    all_errors = [error_pct(pair, scale) for pair in pairs]

    output = {
        "schema_version": 1,
        "source": "matched strict DRAMsim3 and event-model runs",
        "read_latency_scale": scale,
        "write_latency_scale": scale,
        "read_to_write_turnaround": args.read_to_write_turnaround,
        "write_to_read_turnaround": args.write_to_read_turnaround,
        "fit_pair_count": len(train),
        "held_out_pair_count": len(holdout),
        "fit_mean_error_pct": statistics.fmean(train_errors),
        "fit_max_error_pct": max(train_errors),
        "held_out_mean_error_pct": (
            statistics.fmean(holdout_errors) if holdout_errors else None
        ),
        "held_out_max_error_pct": max(holdout_errors) if holdout_errors else None,
        "all_mean_error_pct": statistics.fmean(all_errors),
        "all_max_error_pct": max(all_errors),
        "pairs": [
            {
                "strict": str(pair.strict_path),
                "event": str(pair.event_path),
                "strict_cycles": pair.strict_cycles,
                "uncalibrated_event_cycles": pair.event_cycles,
                "non_memory_floor_cycles": pair.base_cycles,
                "memory_exposure_cycles": pair.memory_exposure,
                "calibrated_prediction_cycles": predict(pair, scale),
                "error_pct": error_pct(pair, scale),
            }
            for pair in pairs
        ],
        "notes": [
            "This is a first-order exposed-memory calibration, not a replacement for held-out validation.",
            "Use matched point clouds, bucket counts, sample counts, and hardware parameters.",
            "Final reporting should include held-out mean and maximum cycle errors.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        f"scale={scale:.6f} pairs={len(pairs)} "
        f"mean_error_pct={output['all_mean_error_pct']:.3f} "
        f"max_error_pct={output['all_max_error_pct']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
