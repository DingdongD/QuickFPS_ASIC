#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from quickfps_cycle.workload import BucketAction, BucketWork, IterationWork, Workload

Point = Tuple[float, float, float]


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits_to_float(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]


def dist2(a: Point, b: Point) -> float:
    dx = f32(a[0] - b[0])
    dy = f32(a[1] - b[1])
    dz = f32(a[2] - b[2])
    return f32(f32(f32(dx * dx) + f32(dy * dy)) + f32(dz * dz))


def box_dist2(point: Point, minimum: Point, maximum: Point) -> float:
    gaps = []
    for value, lower, upper in zip(point, minimum, maximum):
        if value < lower:
            gaps.append(f32(lower - value))
        elif value > upper:
            gaps.append(f32(value - upper))
        else:
            gaps.append(0.0)
    return f32(
        f32(f32(gaps[0] * gaps[0]) + f32(gaps[1] * gaps[1]))
        + f32(gaps[2] * gaps[2])
    )


def load_coords(path: Path) -> List[Point]:
    points: List[Point] = []
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text:
            continue
        value = int(text, 16)
        x = bits_to_float(value & 0xFFFFFFFF)
        y = bits_to_float((value >> 32) & 0xFFFFFFFF)
        z = bits_to_float((value >> 64) & 0xFFFFFFFF)
        points.append((x, y, z))
    if not points:
        raise ValueError("coords.hex contains no points")
    return points


@dataclass
class BucketState:
    bucket_id: int
    point_ptr: int
    point_count: int
    minimum: Point
    maximum: Point
    far_index: int
    far_dist: float = math.inf
    merge_points: List[Point] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.merge_points is None:
            self.merge_points = []


def load_buckets(path: Path) -> List[BucketState]:
    buckets = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            buckets.append(
                BucketState(
                    bucket_id=int(row["bucket"]),
                    point_ptr=int(row["point_ptr"]),
                    point_count=int(row["point_count"]),
                    minimum=(float(row["minx"]), float(row["miny"]), float(row["minz"])),
                    maximum=(float(row["maxx"]), float(row["maxy"]), float(row["maxz"])),
                    far_index=int(row["far_index"]),
                )
            )
    if not buckets:
        raise ValueError("buckets.csv contains no buckets")
    return buckets


def better(distance: float, index: int, best_distance: float, best_index: int) -> bool:
    return distance > best_distance or (
        distance == best_distance and index < best_index
    )


def generate(
    points: Sequence[Point], buckets: List[BucketState], sample_count: int
) -> Tuple[Workload, List[int]]:
    if sample_count < 1 or sample_count > len(points):
        raise ValueError("sample_count must be in [1, point_count]")
    mdt = [math.inf] * len(points)
    selected = [0]
    iterations: List[IterationWork] = []
    current = 0

    for iteration in range(sample_count - 1):
        sample = points[current]
        actions: List[BucketAction] = []
        first_iteration = iteration == 0
        for bucket in buckets:
            far_d_to_sample = dist2(points[bucket.far_index], sample)
            lower_bound = box_dist2(sample, bucket.minimum, bucket.maximum)
            merge_ok = bucket.far_dist < far_d_to_sample
            implicit_ok = bucket.far_dist < lower_bound
            merge_count = len(bucket.merge_points)

            if not first_iteration and merge_ok and implicit_ok:
                actions.append(BucketAction(bucket.bucket_id, "skip", merge_count))
                continue
            if not first_iteration and merge_ok:
                actions.append(BucketAction(bucket.bucket_id, "defer", merge_count))
                bucket.merge_points.append(sample)
                continue

            actions.append(BucketAction(bucket.bucket_id, "issue", merge_count))
            references = list(bucket.merge_points)
            references.append(sample)
            start = bucket.point_ptr
            stop = start + bucket.point_count
            best_index = start
            best_distance = -1.0
            for point_index in range(start, stop):
                value = mdt[point_index]
                for reference in references:
                    value = min(value, dist2(points[point_index], reference))
                mdt[point_index] = value
                if better(value, point_index, best_distance, best_index):
                    best_index = point_index
                    best_distance = value
            bucket.far_index = best_index
            bucket.far_dist = best_distance
            bucket.merge_points.clear()

        iterations.append(IterationWork(iteration, current, actions))
        best_bucket = buckets[0]
        for bucket in buckets[1:]:
            if better(
                bucket.far_dist,
                bucket.far_index,
                best_bucket.far_dist,
                best_bucket.far_index,
            ):
                best_bucket = bucket
        current = best_bucket.far_index
        selected.append(current)

    workload = Workload(
        buckets={
            bucket.bucket_id: BucketWork(
                bucket.bucket_id, bucket.point_ptr, bucket.point_count
            )
            for bucket in buckets
        },
        iterations=iterations,
        metadata={
            "point_count": len(points),
            "sample_count": sample_count,
            "expected_sequence": selected,
            "generator": "cmodel/generate_workload.py",
        },
    )
    workload.validate()
    return workload, selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preprocessed", type=Path, required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    points = load_coords(args.preprocessed / "coords.hex")
    buckets = load_buckets(args.preprocessed / "buckets.csv")
    workload, selected = generate(points, buckets, args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    workload.save(args.output)
    print("sequence=" + ",".join(str(value) for value in selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
