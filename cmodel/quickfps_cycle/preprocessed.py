from __future__ import annotations

import csv
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PIDX_W = 18
MCNT_W = 8
E_MINX = 0
E_MINY = 32
E_MINZ = 64
E_MAXX = 96
E_MAXY = 128
E_MAXZ = 160
E_PTR = 192
E_NUMP = 224
E_FDIST = 336
E_FIDX = 368
E_MCNT = E_FIDX + PIDX_W


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class BucketDescriptor:
    bucket_id: int
    point_ptr: int
    point_count: int
    minimum: Point3
    maximum: Point3
    far_index: int
    far_distance: float = math.inf
    merge_points: List[Point3] = field(default_factory=list)

    @property
    def point_stop(self) -> int:
        return self.point_ptr + self.point_count


@dataclass
class PreprocessedImage:
    coordinates: List[Point3]
    mdt: List[float]
    buckets: List[BucketDescriptor]
    reordered_to_original: List[int]
    manifest: Dict[str, Any] = field(default_factory=dict)
    coord_base: int = 0x0000_0000
    dist_base: int = 0x1000_0000
    result_base: int = 0x2000_0000

    def validate(self) -> None:
        point_count = len(self.coordinates)
        if point_count == 0:
            raise ValueError("preprocessed image contains no coordinates")
        if len(self.mdt) != point_count:
            raise ValueError("MDT length does not match coordinate count")
        if len(self.reordered_to_original) != point_count:
            raise ValueError("reorder map length does not match coordinate count")
        if not self.buckets:
            raise ValueError("preprocessed image contains no buckets")
        expected_ptr = 0
        for expected_id, bucket in enumerate(self.buckets):
            if bucket.bucket_id != expected_id:
                raise ValueError("bucket ids must be dense and zero based")
            if bucket.point_ptr != expected_ptr:
                raise ValueError(
                    f"bucket {bucket.bucket_id} starts at {bucket.point_ptr}, "
                    f"expected contiguous pointer {expected_ptr}"
                )
            if bucket.point_count <= 0:
                raise ValueError(f"bucket {bucket.bucket_id} has no points")
            if bucket.point_stop > point_count:
                raise ValueError(f"bucket {bucket.bucket_id} exceeds point array")
            if not (bucket.point_ptr <= bucket.far_index < bucket.point_stop):
                raise ValueError(f"bucket {bucket.bucket_id} far index is outside the bucket")
            expected_ptr = bucket.point_stop
        if expected_ptr != point_count:
            raise ValueError("bucket ranges do not cover the complete point array")

    def bucket_for_index(self, point_index: int) -> int:
        if not 0 <= point_index < len(self.coordinates):
            raise IndexError(point_index)
        for bucket in self.buckets:
            if bucket.point_ptr <= point_index < bucket.point_stop:
                return bucket.bucket_id
        raise RuntimeError(f"point {point_index} is not covered by any bucket")

    def original_indices(self, reordered_indices: Iterable[int]) -> List[int]:
        return [self.reordered_to_original[index] for index in reordered_indices]

    def clone(self) -> "PreprocessedImage":
        image = PreprocessedImage(
            coordinates=list(self.coordinates),
            mdt=list(self.mdt),
            buckets=[
                BucketDescriptor(
                    bucket_id=bucket.bucket_id,
                    point_ptr=bucket.point_ptr,
                    point_count=bucket.point_count,
                    minimum=bucket.minimum,
                    maximum=bucket.maximum,
                    far_index=bucket.far_index,
                    far_distance=bucket.far_distance,
                    merge_points=list(bucket.merge_points),
                )
                for bucket in self.buckets
            ],
            reordered_to_original=list(self.reordered_to_original),
            manifest=dict(self.manifest),
            coord_base=self.coord_base,
            dist_base=self.dist_base,
            result_base=self.result_base,
        )
        image.validate()
        return image

    @classmethod
    def load(cls, directory: str | Path) -> "PreprocessedImage":
        root = Path(directory)
        coordinates = load_coordinates(root / "coords.hex")
        mdt = load_mdt(root / "dist.hex")
        bucket_hex = root / "buckets.hex"
        buckets = (
            load_buckets_hex(bucket_hex)
            if bucket_hex.exists()
            else load_buckets_csv(root / "buckets.csv")
        )
        reorder = load_reorder_map(root / "reorder_map.txt", len(coordinates))
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        image = cls(coordinates, mdt, buckets, reorder, manifest)
        image.validate()
        return image

    def state_summary(self) -> Dict[str, Any]:
        finite_mdt = [value for value in self.mdt if math.isfinite(value)]
        return {
            "point_count": len(self.coordinates),
            "bucket_count": len(self.buckets),
            "finite_mdt_count": len(finite_mdt),
            "mdt_sum": float(sum(finite_mdt)),
            "bucket_far_indices": [bucket.far_index for bucket in self.buckets],
            "bucket_far_distances": [
                bucket.far_distance if math.isfinite(bucket.far_distance) else None
                for bucket in self.buckets
            ],
            "merge_counts": [len(bucket.merge_points) for bucket in self.buckets],
        }


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def bits_to_float(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value & 0xFFFF_FFFF))[0]


def field(value: int, offset: int, width: int) -> int:
    return (value >> offset) & ((1 << width) - 1)


def dist2(a: Point3, b: Point3) -> float:
    dx = f32(a.x - b.x)
    dy = f32(a.y - b.y)
    dz = f32(a.z - b.z)
    xx = f32(dx * dx)
    yy = f32(dy * dy)
    zz = f32(dz * dz)
    return f32(f32(xx + yy) + zz)


def box_dist2(point: Point3, minimum: Point3, maximum: Point3) -> float:
    gaps = []
    for value, lower, upper in zip(
        point.as_tuple(), minimum.as_tuple(), maximum.as_tuple()
    ):
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


def better(distance: float, index: int, best_distance: float, best_index: int) -> bool:
    return distance > best_distance or (
        distance == best_distance and index < best_index
    )


def load_coordinates(path: Path) -> List[Point3]:
    points: List[Point3] = []
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text:
            continue
        packed = int(text, 16)
        points.append(
            Point3(
                bits_to_float(packed & 0xFFFF_FFFF),
                bits_to_float((packed >> 32) & 0xFFFF_FFFF),
                bits_to_float((packed >> 64) & 0xFFFF_FFFF),
            )
        )
    return points


def load_mdt(path: Path) -> List[float]:
    return [
        bits_to_float(int(line.strip(), 16))
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def load_buckets_hex(path: Path) -> List[BucketDescriptor]:
    buckets: List[BucketDescriptor] = []
    for bucket_id, line in enumerate(path.read_text().splitlines()):
        text = line.strip()
        if not text:
            continue
        packed = int(text, 16)
        merge_count = field(packed, E_MCNT, MCNT_W)
        if merge_count != 0:
            raise ValueError(
                "preprocessed buckets.hex contains a nonzero merge count but no "
                "corresponding merge-point payload"
            )
        buckets.append(
            BucketDescriptor(
                bucket_id=bucket_id,
                point_ptr=field(packed, E_PTR, 32),
                point_count=field(packed, E_NUMP, 16),
                minimum=Point3(
                    bits_to_float(field(packed, E_MINX, 32)),
                    bits_to_float(field(packed, E_MINY, 32)),
                    bits_to_float(field(packed, E_MINZ, 32)),
                ),
                maximum=Point3(
                    bits_to_float(field(packed, E_MAXX, 32)),
                    bits_to_float(field(packed, E_MAXY, 32)),
                    bits_to_float(field(packed, E_MAXZ, 32)),
                ),
                far_index=field(packed, E_FIDX, PIDX_W),
                far_distance=bits_to_float(field(packed, E_FDIST, 32)),
            )
        )
    return buckets


def load_buckets_csv(path: Path) -> List[BucketDescriptor]:
    buckets: List[BucketDescriptor] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            buckets.append(
                BucketDescriptor(
                    bucket_id=int(row["bucket"]),
                    point_ptr=int(row["point_ptr"]),
                    point_count=int(row["point_count"]),
                    minimum=Point3(
                        f32(float(row["minx"])),
                        f32(float(row["miny"])),
                        f32(float(row["minz"])),
                    ),
                    maximum=Point3(
                        f32(float(row["maxx"])),
                        f32(float(row["maxy"])),
                        f32(float(row["maxz"])),
                    ),
                    far_index=int(row["far_index"]),
                )
            )
    return buckets


def load_reorder_map(path: Path, point_count: int) -> List[int]:
    if not path.exists():
        return list(range(point_count))
    values = [-1] * point_count
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text:
            continue
        reordered, original = (int(value) for value in text.split())
        if not 0 <= reordered < point_count:
            raise ValueError(f"invalid reordered index {reordered}")
        if values[reordered] != -1:
            raise ValueError(f"duplicate reordered index {reordered}")
        values[reordered] = original
    if any(value < 0 for value in values):
        raise ValueError("reorder map is incomplete")
    return values
