from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Literal, Optional, Set, Tuple

from .config import AcceleratorConfig, DramConfig
from .memory import BankedDramModel, MemoryBackend, MemoryCompletion, MemoryRequest
from .model import SimulationResult, TraceEvent
from .preprocessed import (
    BucketDescriptor,
    Point3,
    PreprocessedImage,
    better,
    box_dist2,
    dist2,
    f32,
)

DecisionKind = Literal["issue", "defer", "skip"]


@dataclass(frozen=True)
class ClosedLoopDecision:
    bucket_id: int
    kind: DecisionKind
    merge_count: int
    sampled_index: int
    sampled_point: Point3
    references: Tuple[Point3, ...] = ()
    far_to_sample: float = 0.0
    lower_bound: float = 0.0
    forced_issue: bool = False


@dataclass(frozen=True)
class FarPointResult:
    bucket_id: int
    far_index: int
    far_distance: float
    far_point: Point3


@dataclass
class FunctionalChunk:
    index: int
    point_offset: int
    point_count: int
    slot: int
    load_tags: Set[int] = field(default_factory=set)
    write_tags: Set[int] = field(default_factory=set)
    load_scheduled: bool = False
    loaded: bool = False
    computing: bool = False
    compute_done_cycle: Optional[int] = None
    write_scheduled: bool = False
    done: bool = False


@dataclass
class FunctionalPointTask:
    decision: ClosedLoopDecision
    bucket: BucketDescriptor
    chunks: List[FunctionalChunk]
    active_chunk: Optional[int] = None
    completed_chunks: int = 0
    best_index: int = 0
    best_distance: float = -1.0


class _FunctionalPointEngineSystem:
    """Timed Point-Engine with real MDT and far-point state updates.

    Memory timing is modeled by the selected backend. Numeric values live in
    ``PreprocessedImage`` and become architecturally visible when a chunk's
    compute stage completes. The next FPS iteration cannot start until all MDT
    writes have completed, so this ordering is equivalent to write-completion
    visibility for the current single Point-Engine architecture.
    """

    def __init__(
        self,
        config: AcceleratorConfig,
        image: PreprocessedImage,
        memory: MemoryBackend,
        events: List[TraceEvent],
        counters: Counter[str],
    ):
        self.config = config
        self.image = image
        self.memory = memory
        self.events = events
        self.counters = counters
        self.bucket_fifo: Deque[ClosedLoopDecision] = deque()
        self.far_fifo: Deque[FarPointResult] = deque()
        self.task: Optional[FunctionalPointTask] = None
        self._slot_owner: List[Optional[int]] = [None, None]
        self._dma_queue: Deque[Tuple[int, MemoryRequest]] = deque()
        self._tag_owner: Dict[int, Tuple[int, str]] = {}
        self._next_tag = 1

    @staticmethod
    def rtl_point_engine_latency(
        point_count: int, merge_count: int, config: AcceleratorConfig
    ) -> int:
        if point_count <= 0:
            return 1
        batches = math.ceil(point_count / config.pe_rows)
        passes = math.ceil((merge_count + 1) / config.pe_cols)
        return passes * (
            config.merge_load_cycles + batches + config.pe_row_latency
        ) + config.point_ctrl_overhead + config.point_io_pipeline_cycles

    def can_enqueue_bucket(self) -> bool:
        return len(self.bucket_fifo) < self.config.bucket_fifo_depth

    def far_available(self) -> bool:
        return bool(self.far_fifo)

    def enqueue_bucket(self, decision: ClosedLoopDecision, cycle: int) -> None:
        if not self.can_enqueue_bucket():
            raise RuntimeError("bucket FIFO overflow")
        self.bucket_fifo.append(decision)
        self.counters["bucket_fifo_pushes"] += 1
        self.counters["bucket_fifo_max_occupancy"] = max(
            self.counters["bucket_fifo_max_occupancy"], len(self.bucket_fifo)
        )
        self.events.append(
            TraceEvent(
                cycle,
                "bucket_fifo",
                "push",
                {"bucket": decision.bucket_id, "kind": decision.kind},
            )
        )

    def pop_far(self, cycle: int) -> FarPointResult:
        if not self.far_fifo:
            raise RuntimeError("far FIFO underflow")
        result = self.far_fifo.popleft()
        self.counters["far_fifo_pops"] += 1
        self.events.append(
            TraceEvent(
                cycle,
                "far_fifo",
                "pop",
                {
                    "bucket": result.bucket_id,
                    "far_index": result.far_index,
                    "far_distance": result.far_distance,
                },
            )
        )
        return result

    def _make_chunks(self, bucket: BucketDescriptor) -> List[FunctionalChunk]:
        chunks: List[FunctionalChunk] = []
        remaining = bucket.point_count
        offset = 0
        index = 0
        while remaining > 0:
            count = min(remaining, self.config.chunk_points)
            chunks.append(FunctionalChunk(index, offset, count, index & 1))
            remaining -= count
            offset += count
            index += 1
        return chunks

    def _axi_burst_count(self, address: int, size: int) -> int:
        count = 0
        done = 0
        while done < size:
            current = address + done
            bytes_to_4k = 4096 - (current & 0xFFF)
            transfer = min(
                size - done,
                self.config.dma_max_burst_bytes,
                bytes_to_4k,
            )
            done += transfer
            count += 1
        return count

    def _memory_requests(
        self,
        cycle: int,
        address: int,
        size: int,
        is_write: bool,
        stream: str,
        chunk_index: int,
        phase: str,
    ) -> Set[int]:
        tags: Set[int] = set()
        transaction = self.config.dram_transaction_bytes
        first_line = address // transaction
        last_line = (address + size - 1) // transaction
        ready_cycle = cycle + self.config.dma_command_cycles
        for line in range(first_line, last_line + 1):
            line_address = line * transaction
            overlap_start = max(address, line_address)
            overlap_end = min(address + size, line_address + transaction)
            tag = self._next_tag
            self._next_tag += 1
            request = MemoryRequest(
                tag=tag,
                address=line_address,
                size=overlap_end - overlap_start,
                is_write=is_write,
                stream=stream,
                submitted_cycle=ready_cycle,
            )
            self._dma_queue.append((ready_cycle, request))
            self._tag_owner[tag] = (chunk_index, phase)
            tags.add(tag)
        return tags

    def _record_axi_command(
        self, cycle: int, address: int, size: int, stream: str, is_write: bool
    ) -> None:
        bursts = self._axi_burst_count(address, size)
        self.counters["dma_commands"] += 1
        self.counters["axi_bursts"] += bursts
        self.counters[f"{stream}_commands"] += 1
        self.counters[f"{stream}_axi_bursts"] += bursts
        self.events.append(
            TraceEvent(
                cycle,
                "dma",
                "command",
                {
                    "address": address,
                    "bytes": size,
                    "write": is_write,
                    "stream": stream,
                    "axi_bursts": bursts,
                },
            )
        )

    def _schedule_load(
        self, task: FunctionalPointTask, chunk: FunctionalChunk, cycle: int
    ) -> None:
        point_index = task.bucket.point_ptr + chunk.point_offset
        coord_addr = self.image.coord_base + point_index * self.config.coord_bytes_per_point
        dist_addr = self.image.dist_base + point_index * self.config.dist_bytes_per_point
        coord_size = chunk.point_count * self.config.coord_bytes_per_point
        dist_size = chunk.point_count * self.config.dist_bytes_per_point
        self._record_axi_command(cycle, coord_addr, coord_size, "coord_read", False)
        self._record_axi_command(cycle, dist_addr, dist_size, "dist_read", False)
        chunk.load_tags |= self._memory_requests(
            cycle, coord_addr, coord_size, False, "coord_read", chunk.index, "load"
        )
        chunk.load_tags |= self._memory_requests(
            cycle, dist_addr, dist_size, False, "dist_read", chunk.index, "load"
        )
        chunk.load_scheduled = True
        self._slot_owner[chunk.slot] = chunk.index
        self.counters["chunks_load_scheduled"] += 1
        self.events.append(
            TraceEvent(
                cycle,
                "point_engine",
                "chunk_load",
                {
                    "bucket": task.decision.bucket_id,
                    "chunk": chunk.index,
                    "points": chunk.point_count,
                    "slot": chunk.slot,
                },
            )
        )

    def _schedule_write(
        self, task: FunctionalPointTask, chunk: FunctionalChunk, cycle: int
    ) -> None:
        point_index = task.bucket.point_ptr + chunk.point_offset
        address = self.image.dist_base + point_index * self.config.dist_bytes_per_point
        size = chunk.point_count * self.config.dist_bytes_per_point
        self._record_axi_command(cycle, address, size, "dist_write", True)
        chunk.write_tags |= self._memory_requests(
            cycle, address, size, True, "dist_write", chunk.index, "write"
        )
        chunk.write_scheduled = True
        self.counters["chunks_write_scheduled"] += 1
        self.events.append(
            TraceEvent(
                cycle,
                "point_engine",
                "chunk_write",
                {
                    "bucket": task.decision.bucket_id,
                    "chunk": chunk.index,
                    "points": chunk.point_count,
                },
            )
        )

    def _accept_task(self, cycle: int) -> None:
        if self.task is not None or not self.bucket_fifo:
            return
        decision = self.bucket_fifo.popleft()
        bucket = self.image.buckets[decision.bucket_id]
        self.task = FunctionalPointTask(
            decision=decision,
            bucket=bucket,
            chunks=self._make_chunks(bucket),
            best_index=bucket.point_ptr,
        )
        self.counters["point_tasks"] += 1
        self.counters["bucket_fifo_pops"] += 1
        self.events.append(
            TraceEvent(
                cycle,
                "point_engine",
                "accept_bucket",
                {
                    "bucket": decision.bucket_id,
                    "points": bucket.point_count,
                    "merge_count": decision.merge_count,
                },
            )
        )

    def _submit_dma(self, cycle: int) -> None:
        submitted = 0
        while self._dma_queue and submitted < self.config.dma_channels:
            ready_cycle, request = self._dma_queue[0]
            if ready_cycle > cycle:
                break
            if not self.memory.can_accept(request) or not self.memory.submit(request):
                self.counters["dma_backpressure_cycles"] += 1
                break
            self._dma_queue.popleft()
            submitted += 1
            self.counters["dram_transactions"] += 1
            self.counters["dma_transactions"] += 1
            self.events.append(
                TraceEvent(
                    cycle,
                    "dram",
                    "submit",
                    {
                        "tag": request.tag,
                        "address": request.address,
                        "bytes": request.size,
                        "write": request.is_write,
                        "stream": request.stream,
                    },
                )
            )

    def _handle_completions(
        self, cycle: int, completions: Iterable[MemoryCompletion]
    ) -> None:
        completion_list = list(completions)
        if self.task is None:
            if completion_list:
                raise RuntimeError("memory completion without an active point task")
            return
        for completion in completion_list:
            owner = self._tag_owner.pop(completion.tag, None)
            if owner is None:
                raise RuntimeError(f"unknown DMA completion tag {completion.tag}")
            chunk_index, phase = owner
            chunk = self.task.chunks[chunk_index]
            if phase == "load":
                chunk.load_tags.discard(completion.tag)
                if not chunk.load_tags:
                    chunk.loaded = True
                    self.events.append(
                        TraceEvent(
                            cycle,
                            "dma",
                            "load_complete",
                            {"bucket": self.task.decision.bucket_id, "chunk": chunk_index},
                        )
                    )
            elif phase == "write":
                chunk.write_tags.discard(completion.tag)
                if not chunk.write_tags:
                    chunk.done = True
                    self.task.completed_chunks += 1
                    self._slot_owner[chunk.slot] = None
                    self.counters["chunks_completed"] += 1
                    self.events.append(
                        TraceEvent(
                            cycle,
                            "dma",
                            "write_complete",
                            {"bucket": self.task.decision.bucket_id, "chunk": chunk_index},
                        )
                    )
            else:
                raise RuntimeError(f"unknown DMA phase {phase}")

    def _fill_pingpong(self, cycle: int) -> None:
        if self.task is None:
            return
        for slot in range(2):
            if self._slot_owner[slot] is not None:
                continue
            candidate = next(
                (
                    chunk
                    for chunk in self.task.chunks
                    if not chunk.load_scheduled and chunk.slot == slot
                ),
                None,
            )
            if candidate is not None:
                self._schedule_load(self.task, candidate, cycle)

    def _compute_chunk(self, task: FunctionalPointTask, chunk: FunctionalChunk) -> None:
        start = task.bucket.point_ptr + chunk.point_offset
        stop = start + chunk.point_count
        references = task.decision.references
        if not references:
            raise RuntimeError("issued bucket has no distance references")
        for point_index in range(start, stop):
            value = self.image.mdt[point_index]
            for reference in references:
                value = min(value, dist2(self.image.coordinates[point_index], reference))
            value = f32(value)
            if value != self.image.mdt[point_index]:
                self.counters["functional_mdt_updates"] += 1
            self.image.mdt[point_index] = value
            self.counters["functional_distance_evaluations"] += len(references)
            if better(value, point_index, task.best_distance, task.best_index):
                task.best_distance = value
                task.best_index = point_index

    def _advance_compute(self, cycle: int) -> None:
        if self.task is None:
            return
        if self.task.active_chunk is not None:
            chunk = self.task.chunks[self.task.active_chunk]
            if chunk.compute_done_cycle == cycle:
                self._compute_chunk(self.task, chunk)
                chunk.computing = False
                self.task.active_chunk = None
                self.counters["compute_chunks"] += 1
                self.events.append(
                    TraceEvent(
                        cycle,
                        "point_engine",
                        "compute_complete",
                        {
                            "bucket": self.task.decision.bucket_id,
                            "chunk": chunk.index,
                            "best_index": self.task.best_index,
                            "best_distance": self.task.best_distance,
                        },
                    )
                )
                self._schedule_write(self.task, chunk, cycle)
        if self.task.active_chunk is None:
            for chunk in self.task.chunks:
                if chunk.loaded and not chunk.computing and not chunk.write_scheduled:
                    latency = self.rtl_point_engine_latency(
                        chunk.point_count, self.task.decision.merge_count, self.config
                    )
                    chunk.computing = True
                    chunk.compute_done_cycle = cycle + latency
                    self.task.active_chunk = chunk.index
                    self.counters["point_compute_cycles"] += latency
                    self.events.append(
                        TraceEvent(
                            cycle,
                            "point_engine",
                            "compute_start",
                            {
                                "bucket": self.task.decision.bucket_id,
                                "chunk": chunk.index,
                                "latency": latency,
                            },
                        )
                    )
                    break

    def _finish_task(self, cycle: int) -> None:
        if self.task is None or self.task.completed_chunks != len(self.task.chunks):
            return
        if len(self.far_fifo) >= self.config.far_fifo_depth:
            self.counters["far_fifo_backpressure_cycles"] += 1
            return
        result = FarPointResult(
            bucket_id=self.task.decision.bucket_id,
            far_index=self.task.best_index,
            far_distance=self.task.best_distance,
            far_point=self.image.coordinates[self.task.best_index],
        )
        self.far_fifo.append(result)
        self.counters["far_fifo_pushes"] += 1
        self.counters["far_fifo_max_occupancy"] = max(
            self.counters["far_fifo_max_occupancy"], len(self.far_fifo)
        )
        self.events.append(
            TraceEvent(
                cycle,
                "far_fifo",
                "push",
                {
                    "bucket": result.bucket_id,
                    "far_index": result.far_index,
                    "far_distance": result.far_distance,
                },
            )
        )
        self.task = None
        self._slot_owner = [None, None]

    def step(self, cycle: int, completions: Iterable[MemoryCompletion]) -> None:
        self._handle_completions(cycle, completions)
        self._accept_task(cycle)
        self._fill_pingpong(cycle)
        self._advance_compute(cycle)
        self._finish_task(cycle)
        self._submit_dma(cycle)
        if self.task is not None:
            self.counters["point_engine_busy_cycles"] += 1
        if self._dma_queue:
            self.counters["dma_queue_nonempty_cycles"] += 1
        self.counters["dma_queue_max_occupancy"] = max(
            self.counters["dma_queue_max_occupancy"], len(self._dma_queue)
        )

    def idle(self) -> bool:
        return (
            self.task is None
            and not self.bucket_fifo
            and not self.far_fifo
            and not self._dma_queue
            and not self._tag_owner
        )


class ClosedLoopQuickFPSCycleModel:
    """Closed-loop functional and edge-accurate QuickFPS simulator.

    Unlike the trace-driven model, bucket decisions, MDT updates, bucket far
    points, the global far reduction, and the next sampled point are generated
    inside the cycle loop from the KD-tree preprocessing image.
    """

    def __init__(
        self,
        image: PreprocessedImage,
        sample_count: int,
        first_sample: int = 0,
        accelerator: Optional[AcceleratorConfig] = None,
        dram: Optional[DramConfig] = None,
        memory_backend: Optional[MemoryBackend] = None,
        trace_events: bool = True,
    ):
        image.validate()
        if not 1 <= sample_count <= len(image.coordinates):
            raise ValueError("sample_count must be in [1, point_count]")
        if not 0 <= first_sample < len(image.coordinates):
            raise ValueError("first_sample is outside the point array")
        self.image = image.clone()
        self.sample_count = sample_count
        self.first_sample = first_sample
        self.accelerator = accelerator or AcceleratorConfig()
        self.accelerator.validate()
        self.dram = dram or DramConfig()
        self.dram.validate()
        if self.accelerator.dram_transaction_bytes != self.dram.burst_bytes:
            raise ValueError(
                "accelerator dram_transaction_bytes must match DramConfig.burst_bytes"
            )
        self.memory: MemoryBackend = memory_backend or BankedDramModel(self.dram)
        self.trace_events = trace_events

    def _traversal_order(self, sampled_index: int) -> List[int]:
        winner_bucket = self.image.bucket_for_index(sampled_index)
        return [winner_bucket] + [
            bucket.bucket_id
            for bucket in self.image.buckets
            if bucket.bucket_id != winner_bucket
        ]

    def _decide(
        self, bucket_id: int, sampled_index: int, first_iteration: bool
    ) -> ClosedLoopDecision:
        bucket = self.image.buckets[bucket_id]
        sampled_point = self.image.coordinates[sampled_index]
        far_to_sample = dist2(self.image.coordinates[bucket.far_index], sampled_point)
        lower_bound = box_dist2(sampled_point, bucket.minimum, bucket.maximum)
        merge_count = len(bucket.merge_points)
        merge_ok = bucket.far_distance < far_to_sample
        implicit_ok = bucket.far_distance < lower_bound
        forced_issue = False

        if first_iteration or not merge_ok:
            kind: DecisionKind = "issue"
        elif implicit_ok:
            kind = "skip"
        elif merge_count >= self.accelerator.merge_buffer_capacity:
            kind = "issue"
            forced_issue = True
        else:
            kind = "defer"

        references: Tuple[Point3, ...] = ()
        if kind == "issue":
            references = tuple(bucket.merge_points) + (sampled_point,)
        return ClosedLoopDecision(
            bucket_id=bucket_id,
            kind=kind,
            merge_count=merge_count,
            sampled_index=sampled_index,
            sampled_point=sampled_point,
            references=references,
            far_to_sample=far_to_sample,
            lower_bound=lower_bound,
            forced_issue=forced_issue,
        )

    def _apply_nonissue_decision(
        self, decision: ClosedLoopDecision, cycle: int, events: List[TraceEvent]
    ) -> None:
        bucket = self.image.buckets[decision.bucket_id]
        if decision.kind == "defer":
            bucket.merge_points.append(decision.sampled_point)
        events.append(
            TraceEvent(
                cycle,
                "bucket_engine",
                decision.kind,
                {
                    "bucket": decision.bucket_id,
                    "merge_count": len(bucket.merge_points),
                    "far_to_sample": decision.far_to_sample,
                    "lower_bound": decision.lower_bound,
                },
            )
        )

    def _apply_far_result(
        self, result: FarPointResult, cycle: int, events: List[TraceEvent]
    ) -> None:
        bucket = self.image.buckets[result.bucket_id]
        bucket.far_index = result.far_index
        bucket.far_distance = result.far_distance
        bucket.merge_points.clear()
        events.append(
            TraceEvent(
                cycle,
                "bucket_engine",
                "bucket_writeback",
                {
                    "bucket": result.bucket_id,
                    "far_index": result.far_index,
                    "far_distance": result.far_distance,
                },
            )
        )

    def _global_far(self) -> FarPointResult:
        first = self.image.buckets[0]
        best_bucket = first.bucket_id
        best_index = first.far_index
        best_distance = first.far_distance
        for bucket in self.image.buckets[1:]:
            if better(bucket.far_distance, bucket.far_index, best_distance, best_index):
                best_bucket = bucket.bucket_id
                best_index = bucket.far_index
                best_distance = bucket.far_distance
        if not math.isfinite(best_distance):
            raise RuntimeError("global far reduction observed no finite bucket result")
        return FarPointResult(
            bucket_id=best_bucket,
            far_index=best_index,
            far_distance=best_distance,
            far_point=self.image.coordinates[best_index],
        )

    def run(self) -> SimulationResult:
        events: List[TraceEvent] = []
        counters: Counter[str] = Counter()
        point = _FunctionalPointEngineSystem(
            self.accelerator, self.image, self.memory, events, counters
        )
        sampled_indices = [self.first_sample]
        if self.sample_count == 1:
            return SimulationResult(
                cycles=0,
                seconds=0.0,
                iterations=0,
                sampled_indices=sampled_indices,
                counters={},
                memory_stats={},
                events=[],
                config={
                    "accelerator": self.accelerator.to_dict(),
                    "dram": self.dram.to_dict(),
                    "scheduler": "closed-loop-strict-pre-edge",
                    "mode": "closed-loop",
                },
            )

        cycle = 0
        pending_completions: List[MemoryCompletion] = []
        iteration = 0
        current_sample = self.first_sample
        traversal = self._traversal_order(current_sample)
        traversal_index = 0
        cd_pipeline: Deque[Tuple[int, ClosedLoopDecision]] = deque()
        decision_fifo: Deque[ClosedLoopDecision] = deque()
        outstanding = 0
        inject_cooldown = 0
        events.append(
            TraceEvent(
                0,
                "bucket_engine",
                "iteration_start",
                {"iteration": 0, "sampled_index": current_sample},
            )
        )

        while cycle < self.accelerator.max_cycles:
            reserved_before = len(cd_pipeline) + len(decision_fifo)
            input_ready_before = (
                reserved_before < self.accelerator.bucket_decision_fifo_depth
            )
            decision_head_before = decision_fifo[0] if decision_fifo else None
            cd_ready_before = bool(cd_pipeline and cd_pipeline[0][0] <= cycle)
            bucket_ready_before = point.can_enqueue_bucket()
            far_available_before = point.far_available()

            point.step(cycle, pending_completions)
            pending_completions = []

            if far_available_before:
                result = point.pop_far(cycle)
                self._apply_far_result(result, cycle, events)
                outstanding -= 1
                counters["bucket_completions"] += 1
                if outstanding < 0:
                    raise RuntimeError("more bucket completions than issues")

            if decision_head_before is not None:
                decision = decision_head_before
                if decision.kind == "issue":
                    if bucket_ready_before:
                        popped = decision_fifo.popleft()
                        if popped is not decision:
                            raise RuntimeError("decision FIFO head changed within a cycle")
                        self.image.buckets[decision.bucket_id].merge_points.clear()
                        point.enqueue_bucket(decision, cycle)
                        outstanding += 1
                        counters["issued_buckets"] += 1
                        if decision.forced_issue:
                            counters["merge_forced_issue_buckets"] += 1
                        events.append(
                            TraceEvent(
                                cycle,
                                "bucket_engine",
                                "issue",
                                {
                                    "bucket": decision.bucket_id,
                                    "outstanding": outstanding,
                                    "merge_count": decision.merge_count,
                                    "forced": decision.forced_issue,
                                },
                            )
                        )
                    else:
                        counters["bucket_fifo_backpressure_cycles"] += 1
                        counters["decision_fifo_head_stall_cycles"] += 1
                else:
                    popped = decision_fifo.popleft()
                    if popped is not decision:
                        raise RuntimeError("decision FIFO head changed within a cycle")
                    counters[f"{decision.kind}_buckets"] += 1
                    self._apply_nonissue_decision(decision, cycle, events)

            if cd_ready_before:
                _, decision = cd_pipeline.popleft()
                if len(decision_fifo) >= self.accelerator.bucket_decision_fifo_depth:
                    raise RuntimeError("bucket decision FIFO credit invariant failed")
                decision_fifo.append(decision)
                counters["bucket_decision_fifo_pushes"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_decision_fifo",
                        "push",
                        {"bucket": decision.bucket_id, "kind": decision.kind},
                    )
                )

            if inject_cooldown > 0:
                inject_cooldown -= 1
            if (
                traversal_index < len(traversal)
                and inject_cooldown == 0
                and input_ready_before
            ):
                bucket_id = traversal[traversal_index]
                traversal_index += 1
                decision = self._decide(
                    bucket_id, current_sample, first_iteration=(iteration == 0)
                )
                cd_pipeline.append(
                    (cycle + self.accelerator.bucket_cd_latency, decision)
                )
                inject_cooldown = self.accelerator.bucket_issue_ii - 1
                counters["bucket_cd_inputs"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_cd",
                        "accept",
                        {
                            "bucket": bucket_id,
                            "sampled_index": current_sample,
                            "predicted_kind": decision.kind,
                            "far_to_sample": decision.far_to_sample,
                            "lower_bound": decision.lower_bound,
                        },
                    )
                )
            elif (
                traversal_index < len(traversal)
                and inject_cooldown == 0
                and not input_ready_before
            ):
                counters["bucket_decision_credit_stall_cycles"] += 1

            reserved_after = len(cd_pipeline) + len(decision_fifo)
            counters["bucket_decision_fifo_max_occupancy"] = max(
                counters["bucket_decision_fifo_max_occupancy"], len(decision_fifo)
            )
            counters["bucket_reserved_credit_max"] = max(
                counters["bucket_reserved_credit_max"], reserved_after
            )
            if reserved_after > self.accelerator.bucket_decision_fifo_depth:
                raise RuntimeError("reserved bucket credits exceeded configured depth")

            scan_done = (
                traversal_index == len(traversal)
                and not cd_pipeline
                and not decision_fifo
            )
            if scan_done and outstanding == 0 and point.idle() and self.memory.idle():
                counters["iterations_completed"] += 1
                global_far = self._global_far()
                events.append(
                    TraceEvent(
                        cycle,
                        "max_tree",
                        "global_far",
                        {
                            "iteration": iteration,
                            "bucket": global_far.bucket_id,
                            "far_index": global_far.far_index,
                            "far_distance": global_far.far_distance,
                        },
                    )
                )
                current_sample = global_far.far_index
                sampled_indices.append(current_sample)
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_engine",
                        "iteration_complete",
                        {
                            "iteration": iteration,
                            "next_sampled_index": current_sample,
                        },
                    )
                )
                iteration += 1
                if len(sampled_indices) == self.sample_count:
                    cycle += 1
                    break
                traversal = self._traversal_order(current_sample)
                traversal_index = 0
                inject_cooldown = 0
                events.append(
                    TraceEvent(
                        cycle + 1,
                        "bucket_engine",
                        "iteration_start",
                        {"iteration": iteration, "sampled_index": current_sample},
                    )
                )

            pending_completions = self.memory.tick()
            counters["cycles"] += 1
            if cd_pipeline or decision_fifo:
                counters["bucket_pipeline_active_cycles"] += 1
            counters["max_outstanding_buckets"] = max(
                counters["max_outstanding_buckets"], outstanding
            )
            cycle += 1
        else:
            raise TimeoutError(
                f"closed-loop QuickFPS exceeded {self.accelerator.max_cycles} cycles"
            )

        memory_stats = self.memory.stats()
        if not self.trace_events:
            events = []
        return SimulationResult(
            cycles=cycle,
            seconds=cycle / self.accelerator.clock_hz,
            iterations=self.sample_count - 1,
            sampled_indices=sampled_indices,
            counters=dict(counters),
            memory_stats=dict(memory_stats),
            events=events,
            config={
                "accelerator": self.accelerator.to_dict(),
                "dram": self.dram.to_dict(),
                "scheduler": "closed-loop-strict-pre-edge",
                "mode": "closed-loop",
                "sample_count": self.sample_count,
                "first_sample": self.first_sample,
            },
        )
