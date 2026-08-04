from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class AcceleratorConfig:
    clock_hz: int = 1_000_000_000
    bucket_cd_latency: int = 4
    bucket_issue_ii: int = 1
    bucket_fifo_depth: int = 8
    far_fifo_depth: int = 8
    pe_rows: int = 4
    pe_cols: int = 4
    pe_cell_latency: int = 5
    merge_load_cycles: int = 4
    point_ctrl_overhead: int = 2
    chunk_points: int = 256
    coord_bytes_per_point: int = 12
    dist_bytes_per_point: int = 4
    dma_bus_bytes: int = 32
    dma_max_burst_beats: int = 16
    dma_channels: int = 4
    dma_command_cycles: int = 2
    sram_read_latency: int = 1
    sram_write_latency: int = 1
    max_cycles: int = 100_000_000

    @property
    def pe_row_latency(self) -> int:
        return self.pe_cols * self.pe_cell_latency

    def validate(self) -> None:
        positive = {
            "clock_hz": self.clock_hz,
            "bucket_cd_latency": self.bucket_cd_latency,
            "bucket_issue_ii": self.bucket_issue_ii,
            "bucket_fifo_depth": self.bucket_fifo_depth,
            "far_fifo_depth": self.far_fifo_depth,
            "pe_rows": self.pe_rows,
            "pe_cols": self.pe_cols,
            "pe_cell_latency": self.pe_cell_latency,
            "chunk_points": self.chunk_points,
            "dma_bus_bytes": self.dma_bus_bytes,
            "dma_max_burst_beats": self.dma_max_burst_beats,
            "dma_channels": self.dma_channels,
            "max_cycles": self.max_cycles,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")
        if self.pe_rows != 4 or self.pe_cols != 4:
            raise ValueError("the validated QuickFPS datapath is fixed to a 4x4 PE array")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DramConfig:
    channels: int = 1
    banks_per_channel: int = 16
    row_bytes: int = 8192
    burst_bytes: int = 64
    queue_depth: int = 32
    t_rcd: int = 14
    t_cl: int = 14
    t_rp: int = 14
    t_burst: int = 4
    write_recovery: int = 8
    address_mapping: str = "channel-bank-row-column"

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if name == "address_mapping":
                continue
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
