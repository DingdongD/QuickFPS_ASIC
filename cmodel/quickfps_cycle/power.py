from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping


@dataclass(frozen=True)
class ModuleEnergy:
    active_pj_per_cycle: float
    idle_pj_per_cycle: float = 0.0
    event_pj: float = 0.0


class PTPXEnergyModel:
    """Map cycle-model counters to post-synthesis PTPX energy estimates.

    The JSON format intentionally stores energy rather than power.  Convert a
    PTPX average active power ``P`` at clock frequency ``f`` with
    ``active_pj_per_cycle = P / f * 1e12``.  Event-only modules such as DMA
    command issue can use ``event_pj``.
    """

    DEFAULT_COUNTER_MAP = {
        "bucket_engine": "bucket_pipeline_active_cycles",
        "point_engine": "point_engine_busy_cycles",
        "dma": "dma_transactions",
        "dram": "cycles",
    }

    def __init__(self, modules: Mapping[str, ModuleEnergy]):
        self.modules = dict(modules)

    @classmethod
    def load(cls, path: str | Path) -> "PTPXEnergyModel":
        raw = json.loads(Path(path).read_text())
        return cls(
            {
                name: ModuleEnergy(
                    active_pj_per_cycle=float(value.get("active_pj_per_cycle", 0.0)),
                    idle_pj_per_cycle=float(value.get("idle_pj_per_cycle", 0.0)),
                    event_pj=float(value.get("event_pj", 0.0)),
                )
                for name, value in raw["modules"].items()
            }
        )

    def estimate(
        self,
        counters: Mapping[str, int],
        total_cycles: int,
        counter_map: Mapping[str, str] | None = None,
    ) -> Dict[str, float]:
        mapping = dict(self.DEFAULT_COUNTER_MAP)
        if counter_map:
            mapping.update(counter_map)
        result: Dict[str, float] = {}
        total = 0.0
        for name, energy in self.modules.items():
            counter_name = mapping.get(name, "")
            active = int(counters.get(counter_name, 0))
            inactive = max(total_cycles - active, 0)
            value = (
                active * energy.active_pj_per_cycle
                + inactive * energy.idle_pj_per_cycle
            )
            if name == "dma":
                value += int(counters.get("dma_transactions", 0)) * energy.event_pj
            result[f"{name}_pj"] = value
            total += value
        result["total_pj"] = total
        result["total_uj"] = total / 1.0e6
        return result
