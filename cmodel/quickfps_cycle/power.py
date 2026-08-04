from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class ModuleEnergy:
    active_pj_per_cycle: float
    idle_pj_per_cycle: float = 0.0
    event_pj: float = 0.0
    counters: Tuple[str, ...] = ()
    counter_mode: str = "cycle"
    instances: int = 1


class PTPXEnergyModel:
    """Map cycle counters to post-synthesis PTPX energy estimates.

    ``active_pj_per_cycle`` is obtained from VCD-driven PTPX average dynamic
    power divided by the characterization clock.  A module may list multiple
    counters when the same characterized RTL is instantiated more than once;
    for example, one AXI reader model is applied to coordinate and MDT readers.
    """

    DEFAULT_COUNTER_MAP: Mapping[str, Tuple[str, ...]] = {
        "bucket_engine": ("bucket_pipeline_active_cycles",),
        "bucket_decision_pipe": ("bucket_pipeline_active_cycles",),
        "point_engine": ("point_engine_busy_cycles",),
        "pingpong_chunk_ctrl": ("point_engine_busy_cycles",),
        "axi_burst_reader": (
            "coord_reader_busy_cycles",
            "dist_reader_busy_cycles",
        ),
        "axi_burst_writer": ("dist_writer_busy_cycles",),
        "sram_1r1w_ptpx": ("point_engine_busy_cycles",),
        "dma": ("dma_busy_cycles",),
        "dram": ("cycles",),
    }

    def __init__(self, modules: Mapping[str, ModuleEnergy]):
        self.modules = dict(modules)

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
            )
        return cls(modules)

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
                active_cycles = 0
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
        result["total_pj"] = total
        result["total_uj"] = total / 1.0e6
        return result
