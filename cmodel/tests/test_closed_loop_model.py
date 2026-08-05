from __future__ import annotations

import math
import unittest

from generate_workload import generate
from quickfps_cycle.closed_loop import ClosedLoopQuickFPSCycleModel
from quickfps_cycle.config import AcceleratorConfig
from quickfps_cycle.preprocessed import (
    BucketDescriptor,
    Point3,
    PreprocessedImage,
)


def collinear_image() -> PreprocessedImage:
    points = [Point3(float(index), 0.0, 0.0) for index in range(8)]
    buckets = [
        BucketDescriptor(
            bucket_id=0,
            point_ptr=0,
            point_count=4,
            minimum=Point3(0.0, 0.0, 0.0),
            maximum=Point3(3.0, 0.0, 0.0),
            far_index=0,
        ),
        BucketDescriptor(
            bucket_id=1,
            point_ptr=4,
            point_count=4,
            minimum=Point3(4.0, 0.0, 0.0),
            maximum=Point3(7.0, 0.0, 0.0),
            far_index=4,
        ),
    ]
    image = PreprocessedImage(
        coordinates=points,
        mdt=[math.inf] * len(points),
        buckets=buckets,
        reordered_to_original=list(range(len(points))),
        manifest={"sample_count": 4},
    )
    image.validate()
    return image


class ClosedLoopFunctionalTest(unittest.TestCase):
    def test_partition_drives_dynamic_fps_sequence(self) -> None:
        config = AcceleratorConfig(
            chunk_points=4,
            bucket_fifo_depth=2,
            far_fifo_depth=2,
            max_cycles=100_000,
        )
        model = ClosedLoopQuickFPSCycleModel(
            collinear_image(),
            sample_count=4,
            accelerator=config,
        )
        result = model.run()
        self.assertEqual(result.sampled_indices, [0, 7, 3, 5])
        self.assertEqual(result.iterations, 3)
        self.assertEqual(result.counters["bucket_cd_inputs"], 6)
        self.assertEqual(
            result.counters["issued_buckets"],
            result.counters["bucket_completions"],
        )
        self.assertGreater(result.counters["functional_distance_evaluations"], 0)
        self.assertEqual(result.memory_stats["accepted"], result.memory_stats["completed"])
        self.assertTrue(all(math.isfinite(value) for value in model.image.mdt))

    def test_closed_loop_matches_shared_functional_generator(self) -> None:
        image = collinear_image()
        workload, expected = generate(image, sample_count=4)
        result = ClosedLoopQuickFPSCycleModel(image, sample_count=4).run()
        self.assertEqual(result.sampled_indices, expected)
        self.assertEqual(
            [iteration.sampled_index for iteration in workload.iterations],
            expected[:-1],
        )
        predicted = {}
        current_iteration = None
        for event in result.events:
            if event.component == "bucket_engine" and event.event == "iteration_start":
                current_iteration = int(event.data["iteration"])
                predicted[current_iteration] = {}
            elif event.component == "bucket_cd" and event.event == "accept":
                self.assertIsNotNone(current_iteration)
                predicted[current_iteration][int(event.data["bucket"])] = event.data[
                    "predicted_kind"
                ]
        for iteration in workload.iterations:
            expected_actions = {
                action.bucket_id: action.kind for action in iteration.actions
            }
            self.assertEqual(predicted[iteration.iteration], expected_actions)

    def test_original_index_mapping_is_preserved(self) -> None:
        image = collinear_image()
        image.reordered_to_original = [7, 6, 5, 4, 3, 2, 1, 0]
        model = ClosedLoopQuickFPSCycleModel(image, sample_count=4)
        result = model.run()
        self.assertEqual(image.original_indices(result.sampled_indices), [7, 0, 4, 2])

    def test_single_sample_requires_no_accelerator_iteration(self) -> None:
        result = ClosedLoopQuickFPSCycleModel(
            collinear_image(), sample_count=1, first_sample=2
        ).run()
        self.assertEqual(result.sampled_indices, [2])
        self.assertEqual(result.cycles, 0)
        self.assertEqual(result.iterations, 0)


if __name__ == "__main__":
    unittest.main()
