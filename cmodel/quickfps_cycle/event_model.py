from __future__ import annotations

import ctypes
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .config import AcceleratorConfig, DramConfig
from .model import SimulationResult
from .preprocessed import Point3, PreprocessedImage


@dataclass(frozen=True)
class EventDramCalibration:
    read_latency_scale: float = 1.0
    write_latency_scale: float = 1.0
    read_to_write_turnaround: int = 4
    write_to_read_turnaround: int = 4
    source: str = "uncalibrated"
    held_out_mean_error_pct: Optional[float] = None
    held_out_max_error_pct: Optional[float] = None

    @classmethod
    def load(cls, path: str | Path) -> "EventDramCalibration":
        value = json.loads(Path(path).read_text())
        return cls(
            read_latency_scale=float(value.get("read_latency_scale", 1.0)),
            write_latency_scale=float(value.get("write_latency_scale", 1.0)),
            read_to_write_turnaround=int(
                value.get("read_to_write_turnaround", 4)
            ),
            write_to_read_turnaround=int(
                value.get("write_to_read_turnaround", 4)
            ),
            source=str(value.get("source", Path(path).name)),
            held_out_mean_error_pct=(
                float(value["held_out_mean_error_pct"])
                if value.get("held_out_mean_error_pct") is not None
                else None
            ),
            held_out_max_error_pct=(
                float(value["held_out_max_error_pct"])
                if value.get("held_out_max_error_pct") is not None
                else None
            ),
        )

    def validate(self) -> None:
        if self.read_latency_scale <= 0 or self.write_latency_scale <= 0:
            raise ValueError("event DRAM latency scales must be positive")
        if self.read_to_write_turnaround < 0 or self.write_to_read_turnaround < 0:
            raise ValueError("event DRAM turnaround cycles cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "read_latency_scale": self.read_latency_scale,
            "write_latency_scale": self.write_latency_scale,
            "read_to_write_turnaround": self.read_to_write_turnaround,
            "write_to_read_turnaround": self.write_to_read_turnaround,
            "source": self.source,
            "held_out_mean_error_pct": self.held_out_mean_error_pct,
            "held_out_max_error_pct": self.held_out_max_error_pct,
        }


class _Point(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
    ]


class _BucketInit(ctypes.Structure):
    _fields_ = [
        ("point_ptr", ctypes.c_uint32),
        ("point_count", ctypes.c_uint32),
        ("min_x", ctypes.c_float),
        ("min_y", ctypes.c_float),
        ("min_z", ctypes.c_float),
        ("max_x", ctypes.c_float),
        ("max_y", ctypes.c_float),
        ("max_z", ctypes.c_float),
        ("far_index", ctypes.c_uint32),
        ("far_distance", ctypes.c_float),
    ]


class _Config(ctypes.Structure):
    _fields_ = [
        ("point_count", ctypes.c_uint32),
        ("bucket_count", ctypes.c_uint32),
        ("sample_count", ctypes.c_uint32),
        ("first_sample", ctypes.c_uint32),
        ("clock_hz", ctypes.c_uint64),
        ("max_hardware_cycles", ctypes.c_uint64),
        ("max_wall_seconds", ctypes.c_double),
        ("progress_interval", ctypes.c_uint32),
        ("bucket_cd_latency", ctypes.c_uint32),
        ("bucket_issue_ii", ctypes.c_uint32),
        ("bucket_fifo_depth", ctypes.c_uint32),
        ("merge_buffer_capacity", ctypes.c_uint32),
        ("sram_read_latency", ctypes.c_uint32),
        ("sram_write_latency", ctypes.c_uint32),
        ("chunk_points", ctypes.c_uint32),
        ("pe_rows", ctypes.c_uint32),
        ("pe_cols", ctypes.c_uint32),
        ("pe_cell_latency", ctypes.c_uint32),
        ("merge_load_cycles", ctypes.c_uint32),
        ("point_ctrl_overhead", ctypes.c_uint32),
        ("point_io_pipeline_cycles", ctypes.c_uint32),
        ("coord_bytes_per_point", ctypes.c_uint32),
        ("dist_bytes_per_point", ctypes.c_uint32),
        ("point_buffer_capacity_bytes", ctypes.c_uint32),
        ("point_buffer_mode", ctypes.c_uint32),
        ("dma_channels", ctypes.c_uint32),
        ("dma_command_cycles", ctypes.c_uint32),
        ("dram_transaction_bytes", ctypes.c_uint32),
        ("dram_channels", ctypes.c_uint32),
        ("banks_per_channel", ctypes.c_uint32),
        ("row_bytes", ctypes.c_uint32),
        ("burst_bytes", ctypes.c_uint32),
        ("t_rcd", ctypes.c_uint32),
        ("t_cl", ctypes.c_uint32),
        ("t_rp", ctypes.c_uint32),
        ("t_burst", ctypes.c_uint32),
        ("write_recovery", ctypes.c_uint32),
        ("read_to_write_turnaround", ctypes.c_uint32),
        ("write_to_read_turnaround", ctypes.c_uint32),
        ("read_latency_scale", ctypes.c_double),
        ("write_latency_scale", ctypes.c_double),
        ("coord_base", ctypes.c_uint64),
        ("dist_base", ctypes.c_uint64),
    ]


class _BucketState(ctypes.Structure):
    _fields_ = [
        ("point_ptr", ctypes.c_uint32),
        ("point_count", ctypes.c_uint32),
        ("far_index", ctypes.c_uint32),
        ("far_distance", ctypes.c_float),
        ("merge_count", ctypes.c_uint32),
    ]


_STATS_FIELDS = (
    "cycles",
    "iterations",
    "bucket_cd_inputs",
    "issued_buckets",
    "defer_buckets",
    "skip_buckets",
    "merge_forced_issue_buckets",
    "issued_points",
    "issued_merge_points",
    "functional_distance_evaluations",
    "functional_mdt_updates",
    "bucket_scan_cycles",
    "bucket_fifo_stall_cycles",
    "bucket_fifo_max_occupancy",
    "point_tasks",
    "point_compute_cycles",
    "point_engine_busy_cycles",
    "chunks",
    "coord_read_bytes",
    "dist_read_bytes",
    "dist_write_bytes",
    "dram_transactions",
    "dram_row_hits",
    "dram_row_misses",
    "dram_read_transactions",
    "dram_write_transactions",
    "dram_last_completion_cycle",
    "completed_samples",
)


class _Stats(ctypes.Structure):
    _fields_ = [
        *((name, ctypes.c_uint64) for name in _STATS_FIELDS),
        ("point_buffer_resident", ctypes.c_uint32),
    ]


class EventDrivenQuickFPSModel:
    """Full-workload functional simulator with event-level cycle accounting.

    This model executes every FPS iteration and every bucket decision. It does
    not extrapolate from smaller point clouds. The memory backend is a native
    transaction-level bank/row C-model, optionally calibrated against strict
    DRAMsim3 windows.
    """

    def __init__(
        self,
        image: PreprocessedImage,
        sample_count: int,
        library: str | Path,
        *,
        first_sample: int = 0,
        accelerator: Optional[AcceleratorConfig] = None,
        dram: Optional[DramConfig] = None,
        calibration: Optional[EventDramCalibration] = None,
        max_hardware_cycles: int = 10_000_000_000,
        max_wall_seconds: float = 0.0,
        progress_interval: int = 1024,
    ) -> None:
        image.validate()
        self.image = image.clone()
        if not 1 <= sample_count <= len(image.coordinates):
            raise ValueError("sample_count must be in [1, point_count]")
        self.sample_count = sample_count
        self.first_sample = first_sample
        self.accelerator = accelerator or AcceleratorConfig()
        self.accelerator.validate()
        self.dram = dram or DramConfig()
        self.dram.validate()
        self.calibration = calibration or EventDramCalibration()
        self.calibration.validate()
        if max_hardware_cycles <= 0:
            raise ValueError("max_hardware_cycles must be positive")
        if max_wall_seconds < 0:
            raise ValueError("max_wall_seconds cannot be negative")
        if progress_interval < 0:
            raise ValueError("progress_interval cannot be negative")
        self.max_hardware_cycles = max_hardware_cycles
        self.max_wall_seconds = max_wall_seconds
        self.progress_interval = progress_interval
        self.library = Path(library).resolve()
        if not self.library.exists():
            raise FileNotFoundError(self.library)
        self._lib = ctypes.CDLL(str(self.library))
        self._configure_api()

    def _configure_api(self) -> None:
        self._lib.qfps_event_create.argtypes = [
            ctypes.POINTER(_Config),
            ctypes.POINTER(_Point),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(_BucketInit),
        ]
        self._lib.qfps_event_create.restype = ctypes.c_void_p
        self._lib.qfps_event_destroy.argtypes = [ctypes.c_void_p]
        self._lib.qfps_event_destroy.restype = None
        self._lib.qfps_event_run.argtypes = [ctypes.c_void_p]
        self._lib.qfps_event_run.restype = ctypes.c_int
        self._lib.qfps_event_copy_samples.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self._lib.qfps_event_copy_samples.restype = ctypes.c_int
        self._lib.qfps_event_copy_mdt.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self._lib.qfps_event_copy_mdt.restype = ctypes.c_int
        self._lib.qfps_event_get_bucket_state.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_BucketState),
        ]
        self._lib.qfps_event_get_bucket_state.restype = ctypes.c_int
        self._lib.qfps_event_get_stats.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_Stats),
        ]
        self._lib.qfps_event_get_stats.restype = ctypes.c_int
        self._lib.qfps_event_last_error.argtypes = []
        self._lib.qfps_event_last_error.restype = ctypes.c_char_p

    def _error(self, fallback: str) -> str:
        value = self._lib.qfps_event_last_error()
        return value.decode("utf-8", errors="replace") if value else fallback

    def _check(self, status: int, operation: str) -> None:
        if status != 1:
            raise RuntimeError(self._error(operation))

    def _point_buffer_mode(self) -> int:
        return {"auto": 0, "streaming": 1, "resident": 2}[
            self.accelerator.point_buffer_mode
        ]

    def _config(self) -> _Config:
        return _Config(
            len(self.image.coordinates),
            len(self.image.buckets),
            self.sample_count,
            self.first_sample,
            self.accelerator.clock_hz,
            self.max_hardware_cycles,
            self.max_wall_seconds,
            self.progress_interval,
            self.accelerator.bucket_cd_latency,
            self.accelerator.bucket_issue_ii,
            self.accelerator.bucket_fifo_depth,
            self.accelerator.merge_buffer_capacity,
            self.accelerator.sram_read_latency,
            self.accelerator.sram_write_latency,
            self.accelerator.chunk_points,
            self.accelerator.pe_rows,
            self.accelerator.pe_cols,
            self.accelerator.pe_cell_latency,
            self.accelerator.merge_load_cycles,
            self.accelerator.point_ctrl_overhead,
            self.accelerator.point_io_pipeline_cycles,
            self.accelerator.coord_bytes_per_point,
            self.accelerator.dist_bytes_per_point,
            self.accelerator.point_buffer_capacity_bytes,
            self._point_buffer_mode(),
            self.accelerator.dma_channels,
            self.accelerator.dma_command_cycles,
            self.accelerator.dram_transaction_bytes,
            self.dram.channels,
            self.dram.banks_per_channel,
            self.dram.row_bytes,
            self.dram.burst_bytes,
            self.dram.t_rcd,
            self.dram.t_cl,
            self.dram.t_rp,
            self.dram.t_burst,
            self.dram.write_recovery,
            self.calibration.read_to_write_turnaround,
            self.calibration.write_to_read_turnaround,
            self.calibration.read_latency_scale,
            self.calibration.write_latency_scale,
            self.image.coord_base,
            self.image.dist_base,
        )

    def run(self) -> SimulationResult:
        points = (_Point * len(self.image.coordinates))(
            *(_Point(point.x, point.y, point.z) for point in self.image.coordinates)
        )
        mdt = (ctypes.c_float * len(self.image.mdt))(*self.image.mdt)
        buckets = (_BucketInit * len(self.image.buckets))(
            *(
                _BucketInit(
                    bucket.point_ptr,
                    bucket.point_count,
                    bucket.minimum.x,
                    bucket.minimum.y,
                    bucket.minimum.z,
                    bucket.maximum.x,
                    bucket.maximum.y,
                    bucket.maximum.z,
                    bucket.far_index,
                    bucket.far_distance,
                )
                for bucket in self.image.buckets
            )
        )
        config = self._config()
        handle = self._lib.qfps_event_create(
            ctypes.byref(config), points, mdt, buckets
        )
        if not handle:
            raise RuntimeError(self._error("failed to create event simulator"))
        try:
            self._check(self._lib.qfps_event_run(handle), "event simulation failed")
            samples = (ctypes.c_uint32 * self.sample_count)()
            sample_count = ctypes.c_uint32()
            self._check(
                self._lib.qfps_event_copy_samples(
                    handle,
                    samples,
                    self.sample_count,
                    ctypes.byref(sample_count),
                ),
                "failed to copy event samples",
            )
            if sample_count.value != self.sample_count:
                raise RuntimeError(
                    f"event simulator returned {sample_count.value} samples, "
                    f"expected {self.sample_count}"
                )
            mdt_output = (ctypes.c_float * len(self.image.mdt))()
            mdt_count = ctypes.c_uint32()
            self._check(
                self._lib.qfps_event_copy_mdt(
                    handle,
                    mdt_output,
                    len(self.image.mdt),
                    ctypes.byref(mdt_count),
                ),
                "failed to copy event MDT",
            )
            if mdt_count.value != len(self.image.mdt):
                raise RuntimeError("event MDT output length changed")
            self.image.mdt = [float(mdt_output[index]) for index in range(mdt_count.value)]

            for bucket_id, bucket in enumerate(self.image.buckets):
                state = _BucketState()
                self._check(
                    self._lib.qfps_event_get_bucket_state(
                        handle, bucket_id, ctypes.byref(state)
                    ),
                    "failed to copy event bucket state",
                )
                if state.point_ptr != bucket.point_ptr or state.point_count != bucket.point_count:
                    raise RuntimeError("event simulator changed a bucket range")
                bucket.far_index = int(state.far_index)
                bucket.far_distance = float(state.far_distance)
                placeholder = Point3(math.nan, math.nan, math.nan)
                bucket.merge_points = [placeholder] * int(state.merge_count)

            raw_stats = _Stats()
            self._check(
                self._lib.qfps_event_get_stats(handle, ctypes.byref(raw_stats)),
                "failed to copy event stats",
            )
            stats = {name: int(getattr(raw_stats, name)) for name in _STATS_FIELDS}
            stats["point_buffer_resident_mode"] = int(
                raw_stats.point_buffer_resident
            )
            stats["event_driven_model"] = 1
            stats["dram_transactions"] = stats.pop("dram_transactions")
            stats["row_hits"] = stats.pop("dram_row_hits")
            stats["row_misses"] = stats.pop("dram_row_misses")
            stats["issued_buckets"] = stats["issued_buckets"]
            cycles = stats["cycles"]
            memory_stats = {
                "accepted": stats["dram_transactions"],
                "completed": stats["dram_transactions"],
                "row_hits": stats["row_hits"],
                "row_misses": stats["row_misses"],
                "bytes_read": stats["coord_read_bytes"] + stats["dist_read_bytes"],
                "bytes_written": stats["dist_write_bytes"],
                "dram_last_completion_cycle": stats["dram_last_completion_cycle"],
            }
            return SimulationResult(
                cycles=cycles,
                seconds=cycles / self.accelerator.clock_hz,
                iterations=self.sample_count - 1,
                sampled_indices=[int(samples[index]) for index in range(sample_count.value)],
                counters=stats,
                memory_stats=memory_stats,
                events=[],
                config={
                    "accelerator": self.accelerator.to_dict(),
                    "dram": self.dram.to_dict(),
                    "scheduler": "native-event-driven-full-workload",
                    "mode": "closed-loop-event",
                    "event_dram_calibration": self.calibration.to_dict(),
                    "max_hardware_cycles": self.max_hardware_cycles,
                    "max_wall_seconds": self.max_wall_seconds,
                    "progress_interval": self.progress_interval,
                    "event_model_library": str(self.library),
                    "full_workload_executed": True,
                    "extrapolated": False,
                },
            )
        finally:
            self._lib.qfps_event_destroy(handle)
