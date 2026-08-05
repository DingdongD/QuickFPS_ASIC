from __future__ import annotations

import math
import os
import unittest
from pathlib import Path

from quickfps_cycle.config import AcceleratorConfig
from quickfps_cycle.native_closed_loop import NativeStrictClosedLoopQuickFPSCycleModel
from quickfps_cycle.preprocessed import BucketDescriptor, Point3, PreprocessedImage
from quickfps_cycle.summary_closed_loop import SummaryStrictClosedLoopQuickFPSCycleModel


def make_image(point_count: int, bucket_count: int) -> PreprocessedImage:
    if point_count % bucket_count:
        raise ValueError("point_count must be divisible by bucket_count")
    points = [
        Point3(
            float(index),
            float((index * 7) % 11) * 0.125,
            float((index * 5) % 13) * 0.0625,
        )
        for index in range(point_count)
    ]
    per_bucket = point_count // bucket_count
    buckets = []
    for bucket_id in range(bucket_count):
        start = bucket_id * per_bucket
        stop = start + per_bucket
        values = points[start:stop]
        buckets.append(
            BucketDescriptor(
                bucket_id=bucket_id,
                point_ptr=start,
                point_count=per_bucket,
                minimum=Point3(
                    min(point.x for point in values),
                    min(point.y for point in values),
                    min(point.z for point in values),
                ),
                maximum=Point3(
                    max(point.x for point in values),
                    max(point.y for point in values),
                    max(point.z for point in values),
                ),
                far_index=start,
            )
        )
    image = PreprocessedImage(
        coordinates=points,
        mdt=[math.inf] * point_count,
        buckets=buckets,
        reordered_to_original=list(range(point_count)),
        manifest={"sample_count": point_count // 2},
    )
    image.validate()
    return image


class NativeBucketSchedulerDifferentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        value = os.environ.get("QFPS_NATIVE_SCHEDULER_LIB")
        if not value:
            raise unittest.SkipTest("QFPS_NATIVE_SCHEDULER_LIB is not set")
        cls.library = Path(value).resolve()
        if not cls.library.exists():
            raise RuntimeError(f"native scheduler library does not exist: {cls.library}")

    def compare_models(self, config: AcceleratorConfig) -> None:
        source = make_image(32, 8)
        python_model = SummaryStrictClosedLoopQuickFPSCycleModel(
            source,
            sample_count=12,
            accelerator=config,
            trace_events=False,
        )
        native_model = NativeStrictClosedLoopQuickFPSCycleModel(
            source,
            sample_count=12,
            accelerator=config,
            trace_events=False,
            native_scheduler_library=self.library,
        )
        python_result = python_model.run()
        native_result = native_model.run()
        self.assertEqual(native_result.sampled_indices, python_result.sampled_indices)
        self.assertEqual(native_result.cycles, python_result.cycles)
        self.assertEqual(native_model.image.mdt, python_model.image.mdt)
        self.assertEqual(
            native_model.image.state_summary(), python_model.image.state_summary()
        )
        scheduler_counters = (
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
        for name in scheduler_counters:
            self.assertEqual(
                native_result.counters.get(name, 0),
                python_result.counters.get(name, 0),
                name,
            )
        point_counters = (
            "functional_distance_evaluations",
            "functional_mdt_updates",
            "point_tasks",
            "point_engine_busy_cycles",
            "issued_points",
        )
        for name in point_counters:
            self.assertEqual(
                native_result.counters.get(name, 0),
                python_result.counters.get(name, 0),
                name,
            )

    def test_resident_point_buffer_matches_python_scheduler(self) -> None:
        self.compare_models(
            AcceleratorConfig(
                chunk_points=4,
                point_buffer_mode="resident",
                point_buffer_capacity_bytes=4096,
                functional_kernel="scalar",
                bucket_decision_fifo_depth=4,
                bucket_fifo_depth=2,
                far_fifo_depth=2,
                merge_buffer_capacity=4,
            )
        )

    def test_streaming_memory_path_matches_python_scheduler(self) -> None:
        self.compare_models(
            AcceleratorConfig(
                chunk_points=4,
                point_buffer_mode="streaming",
                functional_kernel="scalar",
                bucket_decision_fifo_depth=4,
                bucket_fifo_depth=2,
                far_fifo_depth=2,
                merge_buffer_capacity=4,
                dma_stream_outstanding=4,
            )
        )


if __name__ == "__main__":
    unittest.main()
