from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal

ActionKind = Literal["issue", "defer", "skip"]


@dataclass(frozen=True)
class BucketWork:
    bucket_id: int
    point_ptr: int
    point_count: int

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "BucketWork":
        return cls(
            bucket_id=int(value["bucket_id"]),
            point_ptr=int(value.get("point_ptr", 0)),
            point_count=int(value["point_count"]),
        )


@dataclass(frozen=True)
class BucketAction:
    bucket_id: int
    kind: ActionKind
    merge_count: int = 0

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "BucketAction":
        kind = str(value["kind"])
        if kind not in {"issue", "defer", "skip"}:
            raise ValueError(f"invalid bucket action {kind!r}")
        return cls(
            bucket_id=int(value["bucket_id"]),
            kind=kind,  # type: ignore[arg-type]
            merge_count=int(value.get("merge_count", 0)),
        )


@dataclass(frozen=True)
class IterationWork:
    iteration: int
    sampled_index: int
    actions: List[BucketAction] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "IterationWork":
        return cls(
            iteration=int(value["iteration"]),
            sampled_index=int(value.get("sampled_index", 0)),
            actions=[BucketAction.from_dict(item) for item in value["actions"]],
        )


@dataclass(frozen=True)
class Workload:
    buckets: Dict[int, BucketWork]
    iterations: List[IterationWork]
    coord_base: int = 0x0000_0000
    dist_base: int = 0x1000_0000
    result_base: int = 0x2000_0000
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.buckets:
            raise ValueError("workload contains no buckets")
        for bucket_id, bucket in self.buckets.items():
            if bucket.bucket_id != bucket_id:
                raise ValueError("bucket dictionary key does not match bucket_id")
            if bucket.point_count <= 0:
                raise ValueError(f"bucket {bucket_id} has no points")
        for expected, iteration in enumerate(self.iterations):
            if iteration.iteration != expected:
                raise ValueError("iterations must be dense and zero-based")
            seen = set()
            for action in iteration.actions:
                if action.bucket_id not in self.buckets:
                    raise ValueError(f"unknown bucket {action.bucket_id}")
                if action.bucket_id in seen:
                    raise ValueError(
                        f"bucket {action.bucket_id} appears twice in iteration {expected}"
                    )
                seen.add(action.bucket_id)
                if action.merge_count < 0:
                    raise ValueError("merge_count must be non-negative")

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Workload":
        buckets = {
            item.bucket_id: item
            for item in (BucketWork.from_dict(entry) for entry in value["buckets"])
        }
        workload = cls(
            buckets=buckets,
            iterations=[IterationWork.from_dict(item) for item in value["iterations"]],
            coord_base=int(value.get("coord_base", 0x0000_0000)),
            dist_base=int(value.get("dist_base", 0x1000_0000)),
            result_base=int(value.get("result_base", 0x2000_0000)),
            metadata=dict(value.get("metadata", {})),
        )
        workload.validate()
        return workload

    @classmethod
    def load(cls, path: str | Path) -> "Workload":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "buckets": [asdict(self.buckets[key]) for key in sorted(self.buckets)],
            "iterations": [
                {
                    "iteration": item.iteration,
                    "sampled_index": item.sampled_index,
                    "actions": [asdict(action) for action in item.actions],
                }
                for item in self.iterations
            ],
            "coord_base": self.coord_base,
            "dist_base": self.dist_base,
            "result_base": self.result_base,
            "metadata": self.metadata,
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")


def synthetic_workload(
    bucket_sizes: Iterable[int], iterations: int, issue_all: bool = True
) -> Workload:
    buckets: Dict[int, BucketWork] = {}
    point_ptr = 0
    for bucket_id, point_count in enumerate(bucket_sizes):
        buckets[bucket_id] = BucketWork(bucket_id, point_ptr, int(point_count))
        point_ptr += int(point_count)
    iteration_work = []
    for index in range(iterations):
        actions = [
            BucketAction(
                bucket_id=bucket_id,
                kind="issue" if issue_all else "skip",
                merge_count=index % 5,
            )
            for bucket_id in buckets
        ]
        iteration_work.append(IterationWork(index, 0, actions))
    workload = Workload(buckets=buckets, iterations=iteration_work)
    workload.validate()
    return workload
