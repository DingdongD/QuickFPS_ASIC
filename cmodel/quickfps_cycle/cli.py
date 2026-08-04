from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import AcceleratorConfig, DramConfig
from .model import QuickFPSCycleModel
from .power import PTPXEnergyModel
from .workload import Workload, synthetic_workload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuickFPS cycle-accurate simulator")
    parser.add_argument("--workload", type=Path, help="workload JSON file")
    parser.add_argument(
        "--synthetic-buckets",
        type=str,
        help="comma-separated bucket sizes when no workload JSON is supplied",
    )
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--chunk-points", type=int, default=256)
    parser.add_argument("--bucket-fifo-depth", type=int, default=8)
    parser.add_argument("--far-fifo-depth", type=int, default=8)
    parser.add_argument("--dram-banks", type=int, default=16)
    parser.add_argument("--dram-queue-depth", type=int, default=32)
    parser.add_argument("--clock-hz", type=int, default=1_000_000_000)
    parser.add_argument("--ptpx-energy", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-events", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.workload:
        workload = Workload.load(args.workload)
    else:
        if not args.synthetic_buckets:
            raise SystemExit("provide --workload or --synthetic-buckets")
        sizes = [int(value) for value in args.synthetic_buckets.split(",") if value]
        workload = synthetic_workload(sizes, args.iterations, issue_all=True)

    accelerator = AcceleratorConfig(
        clock_hz=args.clock_hz,
        chunk_points=args.chunk_points,
        bucket_fifo_depth=args.bucket_fifo_depth,
        far_fifo_depth=args.far_fifo_depth,
    )
    dram = DramConfig(
        banks_per_channel=args.dram_banks,
        queue_depth=args.dram_queue_depth,
    )
    result = QuickFPSCycleModel(
        workload,
        accelerator=accelerator,
        dram=dram,
        trace_events=not args.no_events,
    ).run()
    output = result.to_dict(include_events=not args.no_events)
    if args.ptpx_energy:
        output["energy"] = PTPXEnergyModel.load(args.ptpx_energy).estimate(
            result.counters, result.cycles
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        f"cycles={result.cycles} seconds={result.seconds:.9f} "
        f"dma_transactions={result.counters.get('dma_transactions', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
