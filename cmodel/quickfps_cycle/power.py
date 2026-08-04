from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .config import AcceleratorConfig


@dataclass(frozen=True)
class ModuleEnergy:
    active_pj_per_cycle: float
    idle_pj_per_cycle: float = 0.0
    event_pj: float = 0.0
    counters: Tuple[str, ...] = ()
    counter_mode: str = "cycle"
    instances: int = 1
    cell_area: float = 0.0
    composition_group: str = "standalone"
    strict_gate_vcd: bool = False


class PTPXEnergyModel:
    """Map cycle counters to post-synthesis PTPX energy estimates.

    ``active_pj_per_cycle`` is obtained from VCD-driven PTPX average total
    power divided by the characterization clock. ``idle_pj_per_cycle`` is an
    independently supplied idle value; the strict QuickFPS database uses the
    leakage-only lower bound until a dedicated idle gate VCD is available.
    A module may list multiple
    counters when the same characterized RTL is instantiated more than once;
    one AXI reader model is applied to coordinate and MDT reader activity.
    """

    DEFAULT_COUNTER_MAP: Mapping[str, Tuple[str, ...]] = {
        "bucket_engine": ("bucket_pipeline_active_cycles",),
        "bucket_decision_pipe": ("bucket_pipeline_active_cycles",),
        "point_engine": ("point_engine_busy_cycles",),
        "point_engine_top": ("point_compute_cycles",),
        "pingpong_chunk_ctrl": ("point_engine_busy_cycles",),
        "quickfps_stream_subsystem": ("dma_busy_cycles",),
        "axi_burst_reader": (
            "coord_read_busy_cycles",
            "dist_read_busy_cycles",
        ),
        "axi_burst_writer": ("dist_write_busy_cycles",),
        "sram_1r1w_ptpx": ("point_engine_busy_cycles",),
        "dma": ("dma_busy_cycles",),
        "dram": ("cycles",),
    }

    def __init__(
        self,
        modules: Mapping[str, ModuleEnergy],
        clock_hz: float | None = None,
        process: str = "",
        schema_version: int = 1,
        rtl_cycle_validation: Mapping[str, Any] | None = None,
    ):
        self.modules = dict(modules)
        self.clock_hz = clock_hz
        self.process = process
        self.schema_version = schema_version
        self.rtl_cycle_validation = dict(rtl_cycle_validation or {})

    @staticmethod
    def _counter_tuple(value: object) -> Tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Sequence) and all(isinstance(item, str) for item in value):
            return tuple(value)
        raise ValueError(f"invalid counter mapping {value!r}")

    @classmethod
    def load(cls, path: str | Path) -> "PTPXEnergyModel":
        raw = json.loads(Path(path).read_text())
        modules = {}
        for name, value in raw["modules"].items():
            counters = cls._counter_tuple(value.get("counters"))
            instances = int(value.get("instances", max(len(counters), 1)))
            modules[name] = ModuleEnergy(
                active_pj_per_cycle=float(value.get("active_pj_per_cycle", 0.0)),
                idle_pj_per_cycle=float(value.get("idle_pj_per_cycle", 0.0)),
                event_pj=float(value.get("event_pj", 0.0)),
                counters=counters,
                counter_mode=str(value.get("counter_mode", "cycle")),
                instances=instances,
                cell_area=float(value.get("cell_area", 0.0)),
                composition_group=str(value.get("composition_group", "standalone")),
                strict_gate_vcd=bool(value.get("strict_gate_vcd", False)),
            )
        clock_hz = raw.get("clock_hz")
        return cls(
            modules,
            clock_hz=float(clock_hz) if clock_hz is not None else None,
            process=str(raw.get("process", "")),
            schema_version=int(raw.get("schema_version", 1)),
            rtl_cycle_validation=raw.get("rtl_cycle_validation", {}),
        )

    def require_clock(self, clock_hz: float, tolerance: float = 1.0e-9) -> None:
        if self.clock_hz is None:
            raise ValueError("PTPX energy database has no characterization clock")
        relative = abs(self.clock_hz - clock_hz) / max(abs(clock_hz), 1.0)
        if relative > tolerance:
            raise ValueError(
                "PTPX characterization clock does not match simulation clock: "
                f"database={self.clock_hz:g}Hz simulation={clock_hz:g}Hz"
            )

    def require_cycle_contract(self, config: AcceleratorConfig) -> None:
        point = self.rtl_cycle_validation.get("point_engine", {})
        measured_point = point.get("latency")
        if measured_point is not None:
            reference_num_points = int(point.get("reference_num_points", 48))
            reference_merge_count = int(point.get("reference_merge_count", 3))
            reference_rows = int(point.get("pe_rows", config.pe_rows))
            reference_cols = int(point.get("pe_cols", config.pe_cols))
            if (config.pe_rows, config.pe_cols) != (reference_rows, reference_cols):
                raise ValueError(
                    "PTPX cycle contract array shape does not match simulator: "
                    f"database={reference_rows}x{reference_cols} "
                    f"model={config.pe_rows}x{config.pe_cols}"
                )
            batches = math.ceil(reference_num_points / config.pe_rows)
            passes = math.ceil((reference_merge_count + 1) / config.pe_cols)
            modeled_point = passes * (
                config.merge_load_cycles + batches + config.pe_row_latency
            ) + config.point_ctrl_overhead + config.point_io_pipeline_cycles
            if modeled_point != int(measured_point):
                raise ValueError(
                    "PTPX cycle contract does not match Point-Engine model: "
                    f"database={int(measured_point)} model={modeled_point}"
                )

        bucket = self.rtl_cycle_validation.get("bucket_decision_pipe", {})
        measured_bucket = bucket.get("first_latency")
        if measured_bucket is not None:
            modeled_bucket = config.bucket_cd_latency + 1
            if modeled_bucket != int(measured_bucket):
                raise ValueError(
                    "PTPX cycle contract does not match bucket pipeline model: "
                    f"database={int(measured_bucket)} model={modeled_bucket}"
                )

    def estimate(
        self,
        counters: Mapping[str, int],
        total_cycles: int,
        counter_map: Mapping[str, str | Sequence[str]] | None = None,
    ) -> Dict[str, float]:
        overrides = {
            name: self._counter_tuple(value)
            for name, value in (counter_map or {}).items()
        }
        result: Dict[str, float] = {}
        total = 0.0
        modeled_area = 0.0
        for name, energy in self.modules.items():
            counter_names = (
                overrides.get(name)
                or energy.counters
                or self.DEFAULT_COUNTER_MAP.get(name, ())
            )
            active_or_events = sum(int(counters.get(counter, 0)) for counter in counter_names)
            if energy.counter_mode == "event":
                value = active_or_events * energy.event_pj
                value += total_cycles * energy.instances * energy.idle_pj_per_cycle
            elif energy.counter_mode == "cycle":
                capacity_cycles = total_cycles * energy.instances
                active_cycles = min(active_or_events, capacity_cycles)
                inactive_cycles = max(capacity_cycles - active_cycles, 0)
                value = (
                    active_cycles * energy.active_pj_per_cycle
                    + inactive_cycles * energy.idle_pj_per_cycle
                    + active_or_events * energy.event_pj
                )
            else:
                raise ValueError(
                    f"module {name} has unsupported counter_mode {energy.counter_mode!r}"
                )
            result[f"{name}_pj"] = value
            result[f"{name}_active_count"] = float(active_or_events)
            total += value
            modeled_area += energy.cell_area * energy.instances
        result["total_pj"] = total
        result["total_uj"] = total / 1.0e6
        result["modeled_cell_area"] = modeled_area
        return result
