from __future__ import annotations

import json
import math
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple

from .config import AcceleratorConfig, DramConfig
from .memory import (
    BankedDramModel,
    MemoryBackend,
    MemoryCompletion,
    MemoryRequest,
)
from .workload import BucketAction, BucketWork, IterationWork, Workload


@dataclass
class TraceEvent:
    cycle: int
    component: str
    event: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkState:
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
class PointTask:
    action: BucketAction
    bucket: BucketWork
    chunks: List[ChunkState]
    active_chunk: Optional[int] = None
    completed_chunks: int = 0
    waiting_return: bool = False


@dataclass
class SimulationResult:
    cycles: int
    seconds: float
    iterations: int
    sampled_indices: List[int]
    counters: Dict[str, int]
    memory_stats: Dict[str, int]
    events: List[TraceEvent]
    config: Dict[str, Any]

    def to_dict(self, include_events: bool = True) -> Dict[str, Any]:
        value = {
            "cycles": self.cycles,
            "seconds": self.seconds,
            "iterations": self.iterations,
            "sampled_indices": self.sampled_indices,
            "counters": self.counters,
            "memory_stats": self.memory_stats,
            "config": self.config,
        }
        if include_events:
            value["events"] = [asdict(event) for event in self.events]
        return value

    def save(self, path: str | Path, include_events: bool = True) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(include_events=include_events), indent=2) + "\n"
        )


class _PointEngineSystem:
    def __init__(
        self,
        config: AcceleratorConfig,
        workload: Workload,
        memory: MemoryBackend,
        events: List[TraceEvent],
        counters: Counter[str],
    ):
        self.config = config
        self.workload = workload
        self.memory = memory
        self.events = events
        self.counters = counters
        self.bucket_fifo: Deque[BucketAction] = deque()
        self.far_fifo: Deque[int] = deque()
        self.task: Optional[PointTask] = None
        self._slot_owner: List[Optional[int]] = [None, None]
        self._dma_queue: Deque[Tuple[int, MemoryRequest]] = deque()
        self._tag_owner: Dict[int, Tuple[int, str]] = {}
        self._next_tag = 1

    @staticmethod
    def rtl_point_engine_latency(
        point_count: int, merge_count: int, config: AcceleratorConfig
    ) -> int:
        """Latency from bucket acceptance to far-point FIFO push.

        This mirrors ``point_engine_top``: L cycles to load a pass, one point
        batch per cycle, a chain of L five-cycle PEs, then COLLECT and PUSH.
        For R=4, L=4, 48 points, and merge_count=3 the result is 38 cycles,
        matching ``tb_point_engine_top_cycle.v``.
        """
        if point_count <= 0:
            return 1
        batches = math.ceil(point_count / config.pe_rows)
        passes = math.ceil((merge_count + 1) / config.pe_cols)
        return passes * (
            config.merge_load_cycles + batches + config.pe_row_latency
        ) + config.point_ctrl_overhead

    def can_enqueue_bucket(self) -> bool:
        return len(self.bucket_fifo) < self.config.bucket_fifo_depth

    def enqueue_bucket(self, action: BucketAction, cycle: int) -> None:
        if not self.can_enqueue_bucket():
            raise RuntimeError("bucket FIFO overflow")
        self.bucket_fifo.append(action)
        self.counters["bucket_fifo_pushes"] += 1
        self.counters["bucket_fifo_max_occupancy"] = max(
            self.counters["bucket_fifo_max_occupancy"], len(self.bucket_fifo)
        )
        self.events.append(
            TraceEvent(cycle, "bucket_fifo", "push", {"bucket": action.bucket_id})
        )

    def pop_far(self, cycle: int) -> Optional[int]:
        if not self.far_fifo:
            return None
        bucket_id = self.far_fifo.popleft()
        self.counters["far_fifo_pops"] += 1
        self.events.append(
            TraceEvent(cycle, "far_fifo", "pop", {"bucket": bucket_id})
        )
        return bucket_id

    def _make_chunks(self, action: BucketAction, bucket: BucketWork) -> List[ChunkState]:
        del action
        chunks = []
        remaining = bucket.point_count
        offset = 0
        index = 0
        while remaining > 0:
            count = min(remaining, self.config.chunk_points)
            chunks.append(ChunkState(index, offset, count, index & 1))
            offset += count
            remaining -= count
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
        """Lower an AXI byte range into DRAM transaction-sized requests.

        The RTL DMA still observes and counts full AXI bursts.  The memory
        backend sees one request per DRAM transaction (64 B by default), which
        matches one DRAMsim3 ``AddTransaction`` and avoids treating a 512 B AXI
        burst as a single DRAM command.
        """
        tags: Set[int] = set()
        transaction = self.config.dram_transaction_bytes
        first_line = address // transaction
        last_line = (address + size - 1) // transaction
        ready_cycle = cycle + self.config.dma_command_cycles
        for line in range(first_line, last_line + 1):
            line_address = line * transaction
            overlap_start = max(address, line_address)
            overlap_end = min(address + size, line_address + transaction)
            overlap_bytes = overlap_end - overlap_start
            tag = self._next_tag
            self._next_tag += 1
            request = MemoryRequest(
                tag=tag,
                address=line_address,
                size=overlap_bytes,
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
                    "ready_cycle": cycle + self.config.dma_command_cycles,
                },
            )
        )

    def _schedule_load(self, task: PointTask, chunk: ChunkState, cycle: int) -> None:
        point_index = task.bucket.point_ptr + chunk.point_offset
        coord_addr = (
            self.workload.coord_base
            + point_index * self.config.coord_bytes_per_point
        )
        dist_addr = (
            self.workload.dist_base
            + point_index * self.config.dist_bytes_per_point
        )
        coord_size = chunk.point_count * self.config.coord_bytes_per_point
        dist_size = chunk.point_count * self.config.dist_bytes_per_point
        self._record_axi_command(cycle, coord_addr, coord_size, "coord_read", False)
        self._record_axi_command(cycle, dist_addr, dist_size, "dist_read", False)
        chunk.load_tags |= self._memory_requests(
            cycle,
            coord_addr,
            coord_size,
            False,
            "coord_read",
            chunk.index,
            "load",
        )
        chunk.load_tags |= self._memory_requests(
            cycle,
            dist_addr,
            dist_size,
            False,
            "dist_read",
            chunk.index,
            "load",
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
                    "bucket": task.action.bucket_id,
                    "chunk": chunk.index,
                    "points": chunk.point_count,
                    "slot": chunk.slot,
                },
            )
        )

    def _schedule_write(self, task: PointTask, chunk: ChunkState, cycle: int) -> None:
        point_index = task.bucket.point_ptr + chunk.point_offset
        address = (
            self.workload.dist_base
            + point_index * self.config.dist_bytes_per_point
        )
        size = chunk.point_count * self.config.dist_bytes_per_point
        self._record_axi_command(cycle, address, size, "dist_write", True)
        chunk.write_tags |= self._memory_requests(
            cycle,
            address,
            size,
            True,
            "dist_write",
            chunk.index,
            "write",
        )
        chunk.write_scheduled = True
        self.counters["chunks_write_scheduled"] += 1
        self.events.append(
            TraceEvent(
                cycle,
                "point_engine",
                "chunk_write",
                {
                    "bucket": task.action.bucket_id,
                    "chunk": chunk.index,
                    "points": chunk.point_count,
                },
            )
        )

    def _accept_task(self, cycle: int) -> None:
        if self.task is not None or not self.bucket_fifo:
            return
        action = self.bucket_fifo.popleft()
        bucket = self.workload.buckets[action.bucket_id]
        self.task = PointTask(action, bucket, self._make_chunks(action, bucket))
        self.counters["point_tasks"] += 1
        self.counters["bucket_fifo_pops"] += 1
        self.events.append(
            TraceEvent(
                cycle,
                "point_engine",
                "accept_bucket",
                {
                    "bucket": action.bucket_id,
                    "points": bucket.point_count,
                    "merge_count": action.merge_count,
                },
            )
        )

    def _submit_dma(self, cycle: int) -> None:
        submitted = 0
        while self._dma_queue and submitted < self.config.dma_channels:
            ready_cycle, request = self._dma_queue[0]
            if ready_cycle > cycle:
                break
            if not self.memory.can_accept(request):
                self.counters["dma_backpressure_cycles"] += 1
                break
            if not self.memory.submit(request):
                self.counters["dma_backpressure_cycles"] += 1
                break
            self._dma_queue.popleft()
            submitted += 1
            self.counters["dram_transactions"] += 1
            # Keep the original counter name as a compatibility alias for
            # previously generated reports.
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
                            {"bucket": self.task.action.bucket_id, "chunk": chunk_index},
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
                            {"bucket": self.task.action.bucket_id, "chunk": chunk_index},
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
            candidate = None
            for chunk in self.task.chunks:
                if not chunk.load_scheduled and chunk.slot == slot:
                    candidate = chunk
                    break
            if candidate is not None:
                self._schedule_load(self.task, candidate, cycle)

    def _advance_compute(self, cycle: int) -> None:
        if self.task is None:
            return
        if self.task.active_chunk is not None:
            chunk = self.task.chunks[self.task.active_chunk]
            if chunk.compute_done_cycle == cycle:
                chunk.computing = False
                self.task.active_chunk = None
                self.counters["compute_chunks"] += 1
                self.events.append(
                    TraceEvent(
                        cycle,
                        "point_engine",
                        "compute_complete",
                        {"bucket": self.task.action.bucket_id, "chunk": chunk.index},
                    )
                )
                self._schedule_write(self.task, chunk, cycle)
        if self.task.active_chunk is None:
            for chunk in self.task.chunks:
                if chunk.loaded and not chunk.computing and not chunk.write_scheduled:
                    latency = self.rtl_point_engine_latency(
                        chunk.point_count, self.task.action.merge_count, self.config
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
                                "bucket": self.task.action.bucket_id,
                                "chunk": chunk.index,
                                "latency": latency,
                            },
                        )
                    )
                    break

    def _finish_task(self, cycle: int) -> None:
        if self.task is None:
            return
        if self.task.completed_chunks != len(self.task.chunks):
            return
        if len(self.far_fifo) >= self.config.far_fifo_depth:
            self.task.waiting_return = True
            self.counters["far_fifo_backpressure_cycles"] += 1
            return
        bucket_id = self.task.action.bucket_id
        self.far_fifo.append(bucket_id)
        self.counters["far_fifo_pushes"] += 1
        self.counters["far_fifo_max_occupancy"] = max(
            self.counters["far_fifo_max_occupancy"], len(self.far_fifo)
        )
        self.events.append(
            TraceEvent(cycle, "far_fifo", "push", {"bucket": bucket_id})
        )
        self.task = None
        self._slot_owner = [None, None]

    def step(
        self, cycle: int, completions: Iterable[MemoryCompletion]
    ) -> None:
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


class QuickFPSCycleModel:
    def __init__(
        self,
        workload: Workload,
        accelerator: Optional[AcceleratorConfig] = None,
        dram: Optional[DramConfig] = None,
        memory_backend: Optional[MemoryBackend] = None,
        trace_events: bool = True,
    ):
        workload.validate()
        self.workload = workload
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

    def run(self) -> SimulationResult:
        events: List[TraceEvent] = []
        counters: Counter[str] = Counter()
        point = _PointEngineSystem(
            self.accelerator, self.workload, self.memory, events, counters
        )
        cycle = 0
        pending_completions: List[MemoryCompletion] = []
        iteration_index = 0
        action_index = 0
        pipeline: Deque[Tuple[int, BucketAction]] = deque()
        outstanding = 0
        inject_cooldown = 0
        sampled_indices: List[int] = []

        if not self.workload.iterations:
            return SimulationResult(
                cycles=0,
                seconds=0.0,
                iterations=0,
                sampled_indices=[],
                counters={},
                memory_stats={},
                events=[],
                config={
                    "accelerator": self.accelerator.to_dict(),
                    "dram": self.dram.to_dict(),
                },
            )

        current: IterationWork = self.workload.iterations[0]
        sampled_indices.append(current.sampled_index)
        events.append(TraceEvent(0, "bucket_engine", "iteration_start", {"iteration": 0}))

        while cycle < self.accelerator.max_cycles:
            point.step(cycle, pending_completions)
            pending_completions = []

            completed_bucket = point.pop_far(cycle)
            if completed_bucket is not None:
                outstanding -= 1
                counters["bucket_completions"] += 1
                if outstanding < 0:
                    raise RuntimeError("more bucket completions than issues")

            stall_pipeline = False
            if pipeline and pipeline[0][0] <= cycle:
                _, action = pipeline[0]
                if action.kind == "issue":
                    if point.can_enqueue_bucket():
                        pipeline.popleft()
                        point.enqueue_bucket(action, cycle)
                        outstanding += 1
                        counters["issued_buckets"] += 1
                        events.append(
                            TraceEvent(
                                cycle,
                                "bucket_engine",
                                "issue",
                                {"bucket": action.bucket_id, "outstanding": outstanding},
                            )
                        )
                    else:
                        stall_pipeline = True
                        counters["bucket_fifo_backpressure_cycles"] += 1
                else:
                    pipeline.popleft()
                    counters[f"{action.kind}_buckets"] += 1
                    events.append(
                        TraceEvent(
                            cycle,
                            "bucket_engine",
                            action.kind,
                            {"bucket": action.bucket_id},
                        )
                    )

            if not stall_pipeline:
                if inject_cooldown > 0:
                    inject_cooldown -= 1
                if (
                    action_index < len(current.actions)
                    and inject_cooldown == 0
                    and len(pipeline) < self.accelerator.bucket_cd_latency
                ):
                    action = current.actions[action_index]
                    action_index += 1
                    pipeline.append(
                        (cycle + self.accelerator.bucket_cd_latency, action)
                    )
                    inject_cooldown = self.accelerator.bucket_issue_ii - 1
                    counters["bucket_cd_inputs"] += 1
                    events.append(
                        TraceEvent(
                            cycle,
                            "bucket_cd",
                            "accept",
                            {"bucket": action.bucket_id, "kind": action.kind},
                        )
                    )

            scan_done = action_index == len(current.actions) and not pipeline
            if scan_done and outstanding == 0 and point.idle() and self.memory.idle():
                counters["iterations_completed"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_engine",
                        "iteration_complete",
                        {"iteration": current.iteration},
                    )
                )
                iteration_index += 1
                if iteration_index == len(self.workload.iterations):
                    cycle += 1
                    break
                current = self.workload.iterations[iteration_index]
                sampled_indices.append(current.sampled_index)
                action_index = 0
                inject_cooldown = 0
                events.append(
                    TraceEvent(
                        cycle + 1,
                        "bucket_engine",
                        "iteration_start",
                        {"iteration": current.iteration},
                    )
                )

            pending_completions = self.memory.tick()
            counters["cycles"] += 1
            if pipeline:
                counters["bucket_pipeline_active_cycles"] += 1
            counters["max_outstanding_buckets"] = max(
                counters["max_outstanding_buckets"], outstanding
            )
            cycle += 1
        else:
            raise TimeoutError(
                f"QuickFPS cycle model exceeded {self.accelerator.max_cycles} cycles"
            )

        memory_stats = (
            self.memory.stats() if hasattr(self.memory, "stats") else {}
        )
        if not self.trace_events:
            events = []
        return SimulationResult(
            cycles=cycle,
            seconds=cycle / self.accelerator.clock_hz,
            iterations=len(self.workload.iterations),
            sampled_indices=sampled_indices,
            counters=dict(counters),
            memory_stats=dict(memory_stats),
            events=events,
            config={
                "accelerator": self.accelerator.to_dict(),
                "dram": self.dram.to_dict(),
            },
        )
