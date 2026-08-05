from __future__ import annotations

import argparse
import json
from pathlib import Path

from .closed_loop_strict import StrictClosedLoopQuickFPSCycleModel
from .config import AcceleratorConfig, DramConfig
from .dramsim3_clock import ClockScaledDramSim3Backend
from .power import PTPXEnergyModel
from .preprocessed import PreprocessedImage
from .strict_cycle_model import StrictQuickFPSCycleModel
from .workload import Workload, synthetic_workload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Edge-accurate QuickFPS cycle simulator"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--preprocessed", type=Path)
    source.add_argument("--workload", type=Path)
    source.add_argument("--synthetic-buckets", type=str)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--first-sample", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--chunk-points", type=int, default=256)
    parser.add_argument("--bucket-decision-fifo-depth", type=int, default=8)
    parser.add_argument("--bucket-fifo-depth", type=int, default=8)
    parser.add_argument("--far-fifo-depth", type=int, default=8)
    parser.add_argument("--merge-buffer-capacity", type=int, default=32)
    parser.add_argument("--dram-banks", type=int, default=16)
    parser.add_argument("--dram-queue-depth", type=int, default=32)
    parser.add_argument("--clock-hz", type=int, default=1_000_000_000)
    parser.add_argument("--dramsim3-lib", type=Path)
    parser.add_argument("--dramsim3-config", type=Path)
    parser.add_argument(
        "--dramsim3-output-dir",
        type=Path,
        default=Path("build/dramsim3_stats"),
    )
    parser.add_argument("--ptpx-energy", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-events", action="store_true")
    parser.add_argument("--no-golden-check", action="store_true")
    return parser


def _sample_count(args: argparse.Namespace, image: PreprocessedImage) -> int:
    if args.samples is not None:
        return args.samples
    value = int(image.manifest.get("sample_count", 0))
    if value <= 0:
        raise SystemExit(
            "closed-loop mode requires --samples or a positive sample_count in manifest.json"
        )
    return value


def _load_golden(root: Path) -> list[int] | None:
    path = root / "golden_indices.txt"
    if not path.exists():
        return None
    return [int(value) for value in path.read_text().splitlines() if value.strip()]


def main() -> int:
    args = build_parser().parse_args()
    if not (args.preprocessed or args.workload or args.synthetic_buckets):
        raise SystemExit("provide --preprocessed, --workload, or --synthetic-buckets")

    accelerator = AcceleratorConfig(
        clock_hz=args.clock_hz,
        chunk_points=args.chunk_points,
        bucket_decision_fifo_depth=args.bucket_decision_fifo_depth,
        bucket_fifo_depth=args.bucket_fifo_depth,
        far_fifo_depth=args.far_fifo_depth,
        merge_buffer_capacity=args.merge_buffer_capacity,
    )
    dram = DramConfig(
        banks_per_channel=args.dram_banks,
        queue_depth=args.dram_queue_depth,
    )

    memory_backend = None
    if args.dramsim3_lib or args.dramsim3_config:
        if not args.dramsim3_lib or not args.dramsim3_config:
            raise SystemExit(
                "--dramsim3-lib and --dramsim3-config must be supplied together"
            )
        args.dramsim3_output_dir.mkdir(parents=True, exist_ok=True)
        memory_backend = ClockScaledDramSim3Backend(
            args.dramsim3_lib,
            args.dramsim3_config,
            args.dramsim3_output_dir,
            accelerator_clock_hz=args.clock_hz,
        )

    closed_loop_model = None
    image = None
    if args.preprocessed:
        image = PreprocessedImage.load(args.preprocessed)
        closed_loop_model = StrictClosedLoopQuickFPSCycleModel(
            image,
            sample_count=_sample_count(args, image),
            first_sample=args.first_sample,
            accelerator=accelerator,
            dram=dram,
            memory_backend=memory_backend,
            trace_events=not args.no_events,
        )
        result = closed_loop_model.run()
        mode = "closed-loop"
    else:
        if args.workload:
            workload = Workload.load(args.workload)
        else:
            sizes = [
                int(value)
                for value in args.synthetic_buckets.split(",")
                if value
            ]
            workload = synthetic_workload(sizes, args.iterations, issue_all=True)
        result = StrictQuickFPSCycleModel(
            workload,
            accelerator=accelerator,
            dram=dram,
            memory_backend=memory_backend,
            trace_events=not args.no_events,
        ).run()
        mode = "trace-replay"

    output = result.to_dict(include_events=not args.no_events)
    output["mode"] = mode
    output["memory_backend"] = "dramsim3" if memory_backend else "analytical"

    if closed_loop_model is not None and image is not None:
        output["sampled_indices_original"] = image.original_indices(
            result.sampled_indices
        )
        output["preprocessing"] = image.manifest
        output["final_functional_state"] = closed_loop_model.image.state_summary()
        preprocess_seconds = float(image.manifest.get("avg_preprocess_s", 0.0))
        output["latency"] = {
            "preprocess_seconds": preprocess_seconds,
            "accelerator_seconds": result.seconds,
            "end_to_end_seconds": preprocess_seconds + result.seconds,
        }
        golden = _load_golden(args.preprocessed)
        if golden is not None:
            output["golden_indices"] = golden
            output["matches_golden"] = result.sampled_indices == golden
            if not args.no_golden_check and result.sampled_indices != golden:
                raise SystemExit(
                    "closed-loop sampled sequence does not match golden_indices.txt: "
                    f"model={result.sampled_indices} golden={golden}"
                )

    if args.ptpx_energy:
        activity = dict(result.counters)
        activity.update(result.memory_stats)
        energy_model = PTPXEnergyModel.load(args.ptpx_energy)
        energy_model.require_clock(args.clock_hz)
        energy_model.require_cycle_contract(accelerator)
        output["energy"] = energy_model.estimate(
            activity,
            result.cycles,
        )
        output["energy_characterization"] = {
            "clock_hz": energy_model.clock_hz,
            "process": energy_model.process,
            "schema_version": energy_model.schema_version,
        }
        if image is not None:
            preprocess_energy = float(
                image.manifest.get("rapl_dynamic_energy_j", 0.0)
            )
            accelerator_logic_energy = output["energy"]["total_pj"] * 1.0e-12
            output["partial_end_to_end_energy_j"] = {
                "preprocess_dynamic_energy_j": preprocess_energy,
                "accelerator_characterized_logic_energy_j": accelerator_logic_energy,
                "total_j": preprocess_energy + accelerator_logic_energy,
                "excludes": [
                    "SRAM macro energy unless separately characterized",
                    "DDR controller and PHY energy",
                    "DRAM device energy",
                    "initial host-to-device transfer energy",
                ],
            }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        f"mode={mode} cycles={result.cycles} seconds={result.seconds:.9f} "
        f"axi_bursts={result.counters.get('axi_bursts', 0)} "
        f"dram_transactions={result.counters.get('dram_transactions', 0)} "
        f"backend={output['memory_backend']} "
        f"sequence={','.join(str(value) for value in result.sampled_indices)}"
    )
    if memory_backend is not None:
        memory_backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
