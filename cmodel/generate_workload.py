#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import List, Tuple

from quickfps_cycle.preprocessed import PreprocessedImage, better, box_dist2, dist2, f32
from quickfps_cycle.workload import BucketAction, BucketWork, IterationWork, Workload


def generate(
    source: PreprocessedImage,
    sample_count: int,
    merge_buffer_capacity: int = 32,
) -> Tuple[Workload, List[int]]:
    image = source.clone()
    if sample_count < 1 or sample_count > len(image.coordinates):
        raise ValueError("sample_count must be in [1, point_count]")
    if merge_buffer_capacity <= 0:
        raise ValueError("merge_buffer_capacity must be positive")

    selected = [0]
    iterations: List[IterationWork] = []
    current = 0

    for iteration in range(sample_count - 1):
        sample = image.coordinates[current]
        actions: List[BucketAction] = []
        first_iteration = iteration == 0
        for bucket in image.buckets:
            far_to_sample = dist2(image.coordinates[bucket.far_index], sample)
            lower_bound = box_dist2(sample, bucket.minimum, bucket.maximum)
            merge_ok = bucket.far_distance < far_to_sample
            implicit_ok = bucket.far_distance < lower_bound
            merge_count = len(bucket.merge_points)

            if first_iteration or not merge_ok:
                kind = "issue"
            elif implicit_ok:
                kind = "skip"
            elif merge_count >= merge_buffer_capacity:
                kind = "issue"
            else:
                kind = "defer"

            actions.append(BucketAction(bucket.bucket_id, kind, merge_count))
            if kind == "skip":
                continue
            if kind == "defer":
                bucket.merge_points.append(sample)
                continue

            references = list(bucket.merge_points)
            references.append(sample)
            bucket.merge_points.clear()
            best_index = bucket.point_ptr
            best_distance = -1.0
            for point_index in range(bucket.point_ptr, bucket.point_stop):
                value = image.mdt[point_index]
                for reference in references:
                    value = min(
                        value,
                        dist2(image.coordinates[point_index], reference),
                    )
                value = f32(value)
                image.mdt[point_index] = value
                if better(value, point_index, best_distance, best_index):
                    best_index = point_index
                    best_distance = value
            bucket.far_index = best_index
            bucket.far_distance = best_distance

        iterations.append(IterationWork(iteration, current, actions))
        best_bucket = image.buckets[0]
        for bucket in image.buckets[1:]:
            if better(
                bucket.far_distance,
                bucket.far_index,
                best_bucket.far_distance,
                best_bucket.far_index,
            ):
                best_bucket = bucket
        if not math.isfinite(best_bucket.far_distance):
            raise RuntimeError("workload generator observed no finite bucket far point")
        current = best_bucket.far_index
        selected.append(current)

    workload = Workload(
        buckets={
            bucket.bucket_id: BucketWork(
                bucket.bucket_id,
                bucket.point_ptr,
                bucket.point_count,
            )
            for bucket in image.buckets
        },
        iterations=iterations,
        coord_base=image.coord_base,
        dist_base=image.dist_base,
        result_base=image.result_base,
        metadata={
            "point_count": len(image.coordinates),
            "sample_count": sample_count,
            "expected_sequence": selected,
            "merge_buffer_capacity": merge_buffer_capacity,
            "generator": "cmodel/generate_workload.py",
            "bucket_metadata_source": "buckets.hex",
        },
    )
    workload.validate()
    return workload, selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preprocessed", type=Path, required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--merge-buffer-capacity", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    image = PreprocessedImage.load(args.preprocessed)
    workload, selected = generate(
        image,
        args.samples,
        merge_buffer_capacity=args.merge_buffer_capacity,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    workload.save(args.output)
    print("sequence=" + ",".join(str(value) for value in selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
