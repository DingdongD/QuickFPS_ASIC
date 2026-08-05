from __future__ import annotations

import math
import os
import unittest
from pathlib import Path

from quickfps_cycle.config import AcceleratorConfig, DramConfig
from quickfps_cycle.event_model import EventDrivenQuickFPSModel
from quickfps_cycle.preprocessed import BucketDescriptor, Point3, PreprocessedImage
from quickfps_cycle.summary_closed_loop import SummaryStrictClosedLoopQuickFPSCycleModel


def image_fixture(point_count: int = 32, bucket_count: int = 8) -> PreprocessedImage:
    points = [
        Point3(
            float(index) * 0.03125,
            float((index * 7) % 19) * 0.0625,
            float((index * 11) % 23) * 0.03125,
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
        manifest={"sample_count": 12},
    )
    image.validate()
    return image


class EventModelFunctionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        value = os.environ.get("QFPS_EVENT_SIM_LIB")
        if not value:
            raise unittest.SkipTest("QFPS_EVENT_SIM_LIB is not set")
        cls.library = Path(value).resolve()
        if not cls.library.exists():
            raise RuntimeError(f"event simulator library does not exist: {cls.library}")

    def compare(self, point_buffer_mode: str) -> None:
        source = image_fixture()
        accelerator = AcceleratorConfig(
            chunk_points=4,
            bucket_fifo_depth=2,
            far_fifo_depth=2,
            merge_buffer_capacity=4,
            point_buffer_capacity_bytes=4096,
            point_buffer_mode=point_buffer_mode,
            functional_kernel="scalar",
            max_cycles=100_000_000,
        )
        dram = DramConfig(banks_per_channel=8, queue_depth=16)
        strict_model = SummaryStrictClosedLoopQuickFPSCycleModel(
            source,
            sample_count=12,
            accelerator=accelerator,
            dram=dram,
            trace_events=False,
        )
        event_model = EventDrivenQuickFPSModel(
            source,
            12,
            self.library,
            accelerator=accelerator,
            dram=dram,
            max_hardware_cycles=1_000_000_000,
            progress_interval=0,
        )
        strict = strict_model.run()
        event = event_model.run()
        self.assertEqual(event.sampled_indices, strict.sampled_indices)
        self.assertEqual(event_model.image.mdt, strict_model.image.mdt)
        self.assertEqual(event.counters["bucket_cd_inputs"], 11 * 8)
        self.assertEqual(event.counters["completed_samples"], 12)
        self.assertTrue(event.config["full_workload_executed"])
        self.assertFalse(event.config["extrapolated"])
        self.assertGreater(event.cycles, 0)

    def test_resident_function_matches_strict_model(self) -> None:
        self.compare("resident")

    def test_streaming_function_matches_strict_model(self) -> None:
        self.compare("streaming")


if __name__ == "__main__":
    unittest.main()
