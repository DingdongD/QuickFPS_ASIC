from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import AcceleratorConfig, DramConfig
from .event_model import EventDramCalibration, EventDrivenQuickFPSModel
from .preprocessed import PreprocessedImage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Full-workload QuickFPS simulator with native functional execution "
            "and an event-driven calibrated DRAM C-model"
        )
    )
    parser.add_argument("--preprocessed", type=Path, required=True)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--first-sample", type=int, default=0)
    parser.add_argument("--event-sim-lib", type=Path, required=True)
    parser.add_argument("--dram-calibration", type=Path)
    parser.add_argument("--clock-hz", type=int, default=1_000_000_000)
    parser.add_argument("--chunk-points", type=int, default=1024)
    parser.add_argument("--bucket-fifo-depth", type=int, default=8)
    parser.add_argument("--merge-buffer-capacity", type=int, default=32)
    parser.add_argument("--point-buffer-capacity-bytes", type=int, default=16 * 1024)
    parser.add_argument(
        "--point-buffer-mode",
        choices=("auto", "streaming", "resident"),
        default="auto",
    )
    parser.add_argument("--dma-channels", type=int, default=4)
    parser.add_argument("--dram-channels", type=int, default=1)
    parser.add_argument("--dram-banks", type=int, default=16)
    parser.add_argument("--dram-row-bytes", type=int, default=8192)
    parser.add_argument("--dram-queue-depth", type=int, default=32)
    parser.add_argument("--dram-t-rcd", type=int, default=14)
    parser.add_argument("--dram-t-cl", type=int, default=14)
    parser.add_argument("--dram-t-rp", type=int, default=14)
    parser.add_argument("--dram-t-burst", type=int, default=4)
    parser.add_argument("--dram-write-recovery", type=int, default=8)
    parser.add_argument(
        "--max-hardware-cycles", type=int, default=10_000_000_000
    )
    parser.add_argument("--max-wall-seconds", type=float, default=0.0)
    parser.add_argument("--progress-every", type=int, default=1024)
    parser.add_argument("--no-golden-check", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _samples(args: argparse.Namespace, image: PreprocessedImage) -> int:
    if args.samples is not None:
        return args.samples
    value = int(image.manifest.get("sample_count", 0))
    if value <= 0:
        raise SystemExit(
            "provide --samples or use a manifest with a positive sample_count"
        )
    return value


def _golden(root: Path) -> list[int] | None:
    path = root / "golden_indices.txt"
    if not path.exists():
        return None
    return [int(value) for value in path.read_text().splitlines() if value.strip()]


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def main() -> int:
    args = build_parser().parse_args()
    image = PreprocessedImage.load(args.preprocessed)
    sample_count = _samples(args, image)
    accelerator = AcceleratorConfig(
        clock_hz=args.clock_hz,
        chunk_points=args.chunk_points,
        bucket_fifo_depth=args.bucket_fifo_depth,
        merge_buffer_capacity=args.merge_buffer_capacity,
        point_buffer_capacity_bytes=args.point_buffer_capacity_bytes,
        point_buffer_mode=args.point_buffer_mode,
        dma_channels=args.dma_channels,
        max_cycles=min(args.max_hardware_cycles, 2_147_483_647),
    )
    dram = DramConfig(
        channels=args.dram_channels,
        banks_per_channel=args.dram_banks,
        row_bytes=args.dram_row_bytes,
        queue_depth=args.dram_queue_depth,
        t_rcd=args.dram_t_rcd,
        t_cl=args.dram_t_cl,
        t_rp=args.dram_t_rp,
        t_burst=args.dram_t_burst,
        write_recovery=args.dram_write_recovery,
    )
    calibration = (
        EventDramCalibration.load(args.dram_calibration)
        if args.dram_calibration
        else EventDramCalibration()
    )
    model = EventDrivenQuickFPSModel(
        image,
        sample_count,
        args.event_sim_lib,
        first_sample=args.first_sample,
        accelerator=accelerator,
        dram=dram,
        calibration=calibration,
        max_hardware_cycles=args.max_hardware_cycles,
        max_wall_seconds=args.max_wall_seconds,
        progress_interval=args.progress_every,
    )
    result = model.run()
    output = result.to_dict(include_events=False)
    output["mode"] = "closed-loop-event"
    output["memory_backend"] = "calibrated-event-dram-cmodel"
    output["sampled_indices_original"] = image.original_indices(
        result.sampled_indices
    )
    output["final_functional_state"] = model.image.state_summary()
    output["preprocessing"] = image.manifest
    preprocess_seconds = float(image.manifest.get("avg_preprocess_s", 0.0))
    output["latency"] = {
        "preprocess_seconds": preprocess_seconds,
        "accelerator_seconds": result.seconds,
        "end_to_end_seconds": preprocess_seconds + result.seconds,
    }
    counters = result.counters
    iterations = result.iterations
    bucket_inputs = int(counters.get("bucket_cd_inputs", 0))
    issued = int(counters.get("issued_buckets", 0))
    completed_bytes = int(result.memory_stats.get("bytes_read", 0)) + int(
        result.memory_stats.get("bytes_written", 0)
    )
    output["diagnostics"] = {
        "average_issued_buckets_per_iteration": _ratio(issued, iterations),
        "average_issued_points_per_iteration": _ratio(
            int(counters.get("issued_points", 0)), iterations
        ),
        "average_merge_points_per_issue": _ratio(
            int(counters.get("issued_merge_points", 0)), issued
        ),
        "issue_ratio": _ratio(issued, bucket_inputs),
        "defer_ratio": _ratio(
            int(counters.get("defer_buckets", 0)), bucket_inputs
        ),
        "skip_ratio": _ratio(
            int(counters.get("skip_buckets", 0)), bucket_inputs
        ),
        "functional_distance_evaluations": int(
            counters.get("functional_distance_evaluations", 0)
        ),
        "functional_mdt_updates": int(
            counters.get("functional_mdt_updates", 0)
        ),
        "effective_offchip_bandwidth_gbps": (
            completed_bytes / result.seconds / 1.0e9
            if result.seconds > 0
            else 0.0
        ),
        "dram_row_hit_rate": _ratio(
            int(result.memory_stats.get("row_hits", 0)),
            int(result.memory_stats.get("row_hits", 0))
            + int(result.memory_stats.get("row_misses", 0)),
        ),
        "bucket_fifo_stall_cycles": int(
            counters.get("bucket_fifo_stall_cycles", 0)
        ),
        "point_engine_busy_fraction": _ratio(
            int(counters.get("point_engine_busy_cycles", 0)), result.cycles
        ),
        "bucket_scan_fraction": _ratio(
            int(counters.get("bucket_scan_cycles", 0)), result.cycles
        ),
        "full_workload_executed": True,
        "extrapolated": False,
    }
    golden = _golden(args.preprocessed)
    if golden is not None:
        output["golden_indices"] = golden
        output["matches_golden"] = result.sampled_indices == golden
        if not args.no_golden_check and result.sampled_indices != golden:
            raise SystemExit(
                "event-model sequence does not match golden_indices.txt: "
                f"model={result.sampled_indices} golden={golden}"
            )
    output["result_classification"] = {
        "functional_execution": "full-workload",
        "cycle_model": "event-driven",
        "dram_model": "transaction-level bank-row C-model",
        "dram_calibration": calibration.to_dict(),
        "strict_dramsim3": False,
        "extrapolation": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        f"mode=closed-loop-event cycles={result.cycles} "
        f"seconds={result.seconds:.9f} "
        f"iterations={result.iterations} "
        f"avg_issued={output['diagnostics']['average_issued_buckets_per_iteration']:.4f} "
        f"row_hit_rate={output['diagnostics']['dram_row_hit_rate']:.4f} "
        f"extrapolated=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
