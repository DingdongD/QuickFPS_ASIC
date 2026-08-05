from __future__ import annotations

import math
import unittest

from quickfps_cycle.config import AcceleratorConfig
from quickfps_cycle.optimized_closed_loop import (
    OptimizedStrictClosedLoopQuickFPSCycleModel,
)
from quickfps_cycle.preprocessed import BucketDescriptor, Point3, PreprocessedImage


def collinear_image(point_count: int = 8, bucket_count: int = 2) -> PreprocessedImage:
    if point_count % bucket_count:
        raise ValueError("test point count must be divisible by bucket count")
    points = [Point3(float(index), 0.0, 0.0) for index in range(point_count)]
    per_bucket = point_count // bucket_count
    buckets = []
    for bucket_id in range(bucket_count):
        start = bucket_id * per_bucket
        stop = start + per_bucket
        buckets.append(
            BucketDescriptor(
                bucket_id=bucket_id,
                point_ptr=start,
                point_count=per_bucket,
                minimum=points[start],
                maximum=points[stop - 1],
                far_index=start,
            )
        )
    image = PreprocessedImage(
        coordinates=points,
        mdt=[math.inf] * point_count,
        buckets=buckets,
        reordered_to_original=list(range(point_count)),
        manifest={"sample_count": min(4, point_count)},
    )
    image.validate()
    return image


class PointBufferResidencyTest(unittest.TestCase):
    def test_auto_mode_keeps_small_cloud_on_chip(self) -> None:
        config = AcceleratorConfig(
            chunk_points=4,
            point_buffer_capacity_bytes=16 * 1024,
            point_buffer_mode="auto",
            functional_kernel="scalar",
            bucket_fifo_depth=2,
            far_fifo_depth=2,
        )
        result = OptimizedStrictClosedLoopQuickFPSCycleModel(
            collinear_image(), sample_count=4, accelerator=config
        ).run()
        self.assertEqual(result.sampled_indices, [0, 7, 3, 5])
        self.assertEqual(result.counters["point_buffer_resident_mode"], 1)
        self.assertEqual(result.counters.get("dram_transactions", 0), 0)
        self.assertGreater(result.counters["point_buffer_bytes_read"], 0)
        self.assertGreater(result.counters["point_buffer_bytes_written"], 0)
        self.assertEqual(result.memory_stats["accepted"], 0)
        self.assertEqual(result.memory_stats["completed"], 0)

    def test_streaming_mode_preserves_off_chip_traffic(self) -> None:
        config = AcceleratorConfig(
            chunk_points=4,
            point_buffer_mode="streaming",
            functional_kernel="scalar",
            bucket_fifo_depth=2,
            far_fifo_depth=2,
            dma_stream_outstanding=4,
        )
        result = OptimizedStrictClosedLoopQuickFPSCycleModel(
            collinear_image(), sample_count=4, accelerator=config
        ).run()
        self.assertEqual(result.sampled_indices, [0, 7, 3, 5])
        self.assertEqual(result.counters["point_buffer_streaming_mode"], 1)
        self.assertGreater(result.counters["dram_transactions"], 0)
        for stream in ("coord_read", "dist_read", "dist_write"):
            self.assertGreater(
                result.counters[f"{stream}_submitted_transactions"], 0
            )
            self.assertEqual(
                result.counters[f"{stream}_submitted_transactions"],
                result.counters[f"{stream}_completed_transactions"],
            )
            self.assertLessEqual(
                result.counters[f"{stream}_outstanding_max"], 4
            )
        self.assertGreater(result.counters["dma_arbiter_grants"], 0)
        self.assertEqual(
            result.memory_stats["accepted"], result.memory_stats["completed"]
        )


class FunctionalKernelTest(unittest.TestCase):
    def test_numpy_and_scalar_sequences_match_when_numpy_is_available(self) -> None:
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("NumPy is not installed")
        common = dict(
            chunk_points=4,
            point_buffer_mode="resident",
            point_buffer_capacity_bytes=16 * 1024,
            bucket_fifo_depth=2,
            far_fifo_depth=2,
        )
        scalar_model = OptimizedStrictClosedLoopQuickFPSCycleModel(
            collinear_image(),
            sample_count=4,
            accelerator=AcceleratorConfig(functional_kernel="scalar", **common),
        )
        numpy_model = OptimizedStrictClosedLoopQuickFPSCycleModel(
            collinear_image(),
            sample_count=4,
            accelerator=AcceleratorConfig(functional_kernel="numpy", **common),
        )
        scalar = scalar_model.run()
        vectorized = numpy_model.run()
        self.assertEqual(vectorized.sampled_indices, scalar.sampled_indices)
        self.assertEqual(vectorized.sampled_indices, [0, 7, 3, 5])
        self.assertEqual(numpy_model.image.mdt, scalar_model.image.mdt)
        self.assertGreater(vectorized.counters["functional_numpy_chunks"], 0)


if __name__ == "__main__":
    unittest.main()
