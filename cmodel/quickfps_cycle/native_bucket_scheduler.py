from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .config import AcceleratorConfig
from .preprocessed import PreprocessedImage


class _Config(ctypes.Structure):
    _fields_ = [
        ("point_count", ctypes.c_uint32),
        ("bucket_count", ctypes.c_uint32),
        ("sample_count", ctypes.c_uint32),
        ("first_sample", ctypes.c_uint32),
        ("bucket_cd_latency", ctypes.c_uint32),
        ("bucket_issue_ii", ctypes.c_uint32),
        ("bucket_decision_fifo_depth", ctypes.c_uint32),
        ("merge_buffer_capacity", ctypes.c_uint32),
        ("sram_read_latency", ctypes.c_uint32),
        ("sram_write_latency", ctypes.c_uint32),
    ]


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


class _FarInput(ctypes.Structure):
    _fields_ = [
        ("valid", ctypes.c_uint32),
        ("bucket_id", ctypes.c_uint32),
        ("far_index", ctypes.c_uint32),
        ("far_distance", ctypes.c_float),
    ]


class _StepInput(ctypes.Structure):
    _fields_ = [
        ("cycle", ctypes.c_uint64),
        ("bucket_fifo_ready_before", ctypes.c_uint32),
        ("external_idle_after_point_step", ctypes.c_uint32),
        ("far", _FarInput),
    ]


class _StepOutput(ctypes.Structure):
    _fields_ = [
        ("issue_valid", ctypes.c_uint32),
        ("issue_bucket_id", ctypes.c_uint32),
        ("issue_merge_count", ctypes.c_uint32),
        ("issue_sampled_index", ctypes.c_uint32),
        ("issue_reference_count", ctypes.c_uint32),
        ("issue_forced", ctypes.c_uint32),
        ("iteration_completed", ctypes.c_uint32),
        ("completed_iteration", ctypes.c_uint32),
        ("next_sampled_index", ctypes.c_uint32),
        ("simulation_done", ctypes.c_uint32),
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
    "bucket_cd_inputs",
    "bucket_decision_fifo_pushes",
    "bucket_decision_fifo_max_occupancy",
    "bucket_reserved_credit_max",
    "bucket_fetch_max_occupancy",
    "bucket_decision_credit_stall_cycles",
    "bucket_fifo_backpressure_cycles",
    "decision_fifo_head_stall_cycles",
    "bucket_buffer_read_requests",
    "bucket_buffer_read_responses",
    "bucket_buffer_read_stall_cycles",
    "bucket_buffer_read_busy_cycles",
    "bucket_buffer_write_requests",
    "bucket_buffer_write_commits",
    "bucket_buffer_write_busy_cycles",
    "bucket_pipeline_active_cycles",
    "issued_buckets",
    "defer_buckets",
    "skip_buckets",
    "merge_forced_issue_buckets",
    "bucket_completions",
    "max_outstanding_buckets",
    "iterations_completed",
)


class _Stats(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in _STATS_FIELDS]


@dataclass(frozen=True)
class NativeIssue:
    bucket_id: int
    merge_count: int
    sampled_index: int
    reference_indices: tuple[int, ...]
    forced: bool


@dataclass(frozen=True)
class NativeStepResult:
    issue: Optional[NativeIssue]
    iteration_completed: bool
    completed_iteration: int
    next_sampled_index: int
    simulation_done: bool


class NativeBucketScheduler:
    """C++ strict Bucket-Engine scheduler exposed through a small C ABI."""

    def __init__(
        self,
        library: str | Path,
        image: PreprocessedImage,
        accelerator: AcceleratorConfig,
        sample_count: int,
        first_sample: int,
    ) -> None:
        image.validate()
        accelerator.validate()
        self._image = image
        self._library_path = Path(library).resolve()
        self._lib = ctypes.CDLL(str(self._library_path))
        self._configure_api()
        points = (_Point * len(image.coordinates))(
            *(_Point(point.x, point.y, point.z) for point in image.coordinates)
        )
        buckets = (_BucketInit * len(image.buckets))(
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
                for bucket in image.buckets
            )
        )
        config = _Config(
            len(image.coordinates),
            len(image.buckets),
            sample_count,
            first_sample,
            accelerator.bucket_cd_latency,
            accelerator.bucket_issue_ii,
            accelerator.bucket_decision_fifo_depth,
            accelerator.merge_buffer_capacity,
            accelerator.sram_read_latency,
            accelerator.sram_write_latency,
        )
        self._handle = self._lib.qfps_native_scheduler_create(
            ctypes.byref(config), points, buckets
        )
        if not self._handle:
            raise RuntimeError(self._last_error("failed to create native scheduler"))
        self._closed = False

    def _configure_api(self) -> None:
        self._lib.qfps_native_scheduler_create.argtypes = [
            ctypes.POINTER(_Config),
            ctypes.POINTER(_Point),
            ctypes.POINTER(_BucketInit),
        ]
        self._lib.qfps_native_scheduler_create.restype = ctypes.c_void_p
        self._lib.qfps_native_scheduler_destroy.argtypes = [ctypes.c_void_p]
        self._lib.qfps_native_scheduler_destroy.restype = None
        self._lib.qfps_native_scheduler_step.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_StepInput),
            ctypes.POINTER(_StepOutput),
        ]
        self._lib.qfps_native_scheduler_step.restype = ctypes.c_int
        self._lib.qfps_native_scheduler_copy_issue_references.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self._lib.qfps_native_scheduler_copy_issue_references.restype = ctypes.c_int
        self._lib.qfps_native_scheduler_get_bucket_state.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_BucketState),
        ]
        self._lib.qfps_native_scheduler_get_bucket_state.restype = ctypes.c_int
        self._lib.qfps_native_scheduler_copy_bucket_merge_indices.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self._lib.qfps_native_scheduler_copy_bucket_merge_indices.restype = ctypes.c_int
        self._lib.qfps_native_scheduler_get_stats.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_Stats),
        ]
        self._lib.qfps_native_scheduler_get_stats.restype = ctypes.c_int
        self._lib.qfps_native_scheduler_last_error.argtypes = []
        self._lib.qfps_native_scheduler_last_error.restype = ctypes.c_char_p

    def _last_error(self, fallback: str) -> str:
        value = self._lib.qfps_native_scheduler_last_error()
        return value.decode("utf-8", errors="replace") if value else fallback

    def _check(self, status: int, operation: str) -> None:
        if status != 1:
            raise RuntimeError(self._last_error(operation))

    def _copy_issue_references(self, count: int) -> tuple[int, ...]:
        if count == 0:
            return ()
        values = (ctypes.c_uint32 * count)()
        copied = ctypes.c_uint32()
        self._check(
            self._lib.qfps_native_scheduler_copy_issue_references(
                self._handle, values, count, ctypes.byref(copied)
            ),
            "failed to copy native issue references",
        )
        if copied.value != count:
            raise RuntimeError(
                f"native issue reference count changed: {copied.value} != {count}"
            )
        return tuple(int(values[index]) for index in range(count))

    def step(
        self,
        cycle: int,
        *,
        bucket_fifo_ready_before: bool,
        external_idle_after_point_step: bool,
        far_result: Optional[Any] = None,
    ) -> NativeStepResult:
        if self._closed:
            raise RuntimeError("native scheduler is closed")
        far = _FarInput()
        if far_result is not None:
            far = _FarInput(
                1,
                int(far_result.bucket_id),
                int(far_result.far_index),
                float(far_result.far_distance),
            )
        input_value = _StepInput(
            cycle,
            int(bucket_fifo_ready_before),
            int(external_idle_after_point_step),
            far,
        )
        output = _StepOutput()
        self._check(
            self._lib.qfps_native_scheduler_step(
                self._handle, ctypes.byref(input_value), ctypes.byref(output)
            ),
            "native scheduler step failed",
        )
        issue = None
        if output.issue_valid:
            references = self._copy_issue_references(output.issue_reference_count)
            issue = NativeIssue(
                bucket_id=int(output.issue_bucket_id),
                merge_count=int(output.issue_merge_count),
                sampled_index=int(output.issue_sampled_index),
                reference_indices=references,
                forced=bool(output.issue_forced),
            )
        return NativeStepResult(
            issue=issue,
            iteration_completed=bool(output.iteration_completed),
            completed_iteration=int(output.completed_iteration),
            next_sampled_index=int(output.next_sampled_index),
            simulation_done=bool(output.simulation_done),
        )

    def stats(self) -> Dict[str, int]:
        value = _Stats()
        self._check(
            self._lib.qfps_native_scheduler_get_stats(
                self._handle, ctypes.byref(value)
            ),
            "failed to read native scheduler stats",
        )
        return {name: int(getattr(value, name)) for name in _STATS_FIELDS}

    def _copy_merge_indices(self, bucket_id: int, count: int) -> Sequence[int]:
        if count == 0:
            return ()
        values = (ctypes.c_uint32 * count)()
        copied = ctypes.c_uint32()
        self._check(
            self._lib.qfps_native_scheduler_copy_bucket_merge_indices(
                self._handle,
                bucket_id,
                values,
                count,
                ctypes.byref(copied),
            ),
            "failed to copy native merge indices",
        )
        if copied.value != count:
            raise RuntimeError(
                f"native merge count changed: {copied.value} != {count}"
            )
        return tuple(int(values[index]) for index in range(count))

    def sync_image(self, image: PreprocessedImage) -> None:
        if len(image.buckets) != len(self._image.buckets):
            raise ValueError("native scheduler image bucket count changed")
        for bucket_id, bucket in enumerate(image.buckets):
            state = _BucketState()
            self._check(
                self._lib.qfps_native_scheduler_get_bucket_state(
                    self._handle, bucket_id, ctypes.byref(state)
                ),
                "failed to read native bucket state",
            )
            if state.point_ptr != bucket.point_ptr or state.point_count != bucket.point_count:
                raise RuntimeError("native bucket range changed unexpectedly")
            bucket.far_index = int(state.far_index)
            bucket.far_distance = float(state.far_distance)
            merge_indices = self._copy_merge_indices(bucket_id, state.merge_count)
            bucket.merge_points = [image.coordinates[index] for index in merge_indices]

    @property
    def library_path(self) -> Path:
        return self._library_path

    def close(self) -> None:
        if not self._closed:
            self._lib.qfps_native_scheduler_destroy(self._handle)
            self._closed = True

    def __enter__(self) -> "NativeBucketScheduler":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        del exc_type, exc, traceback
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
