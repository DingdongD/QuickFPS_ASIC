from __future__ import annotations

import threading
from collections import Counter, deque
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

from . import closed_loop_strict as strict_module
from .closed_loop import (
    FunctionalChunk,
    FunctionalPointTask,
    _FunctionalPointEngineSystem,
)
from .memory import MemoryCompletion, MemoryRequest
from .model import SimulationResult, TraceEvent
from .preprocessed import better, dist2, f32


_DMA_STREAMS = ("coord_read", "dist_read", "dist_write")
_INSTALL_LOCK = threading.Lock()


class _OptimizedFunctionalPointEngineSystem(_FunctionalPointEngineSystem):
    """Functional Point-Engine with a resident-buffer path and fair DMA queues.

    The original closed-loop implementation used one FIFO for coordinate reads,
    MDT reads, and MDT writes.  That imposed head-of-line blocking that is not
    representative of the independent QuickFPS DMA streams.  This model keeps
    one queue and one outstanding window per stream and arbitrates ready
    transactions in round-robin order.

    When the complete coordinate-plus-MDT working set fits in the configured
    16-KB Point Buffer, ``point_buffer_mode=auto`` uses local synchronous SRAM
    accesses during the timed FPS window.  The initial host/DRAM preload remains
    an explicitly excluded system term, matching the existing simulator's
    separation between preprocessing/initial transfer and accelerator sampling.
    """

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._dma_queues: Dict[str, Deque[Tuple[int, MemoryRequest]]] = {
            stream: deque() for stream in _DMA_STREAMS
        }
        self._dma_rr_cursor = 0
        self._stream_outstanding: Counter[str] = Counter()
        self._local_load_ready: Dict[int, int] = {}
        self._local_write_ready: Dict[int, int] = {}

        working_set_bytes = (
            len(self.image.coordinates) * self.config.point_bytes_per_point
        )
        mode = self.config.point_buffer_mode
        self._resident_point_buffer = mode == "resident" or (
            mode == "auto"
            and working_set_bytes <= self.config.point_buffer_capacity_bytes
        )
        if mode == "resident" and working_set_bytes > self.config.point_buffer_capacity_bytes:
            raise ValueError(
                "resident point-buffer mode requested for a working set larger "
                f"than the configured capacity: {working_set_bytes} > "
                f"{self.config.point_buffer_capacity_bytes} bytes"
            )
        self.counters["point_buffer_working_set_bytes"] = working_set_bytes
        self.counters["point_buffer_capacity_bytes"] = (
            self.config.point_buffer_capacity_bytes
        )
        if self._resident_point_buffer:
            self.counters["point_buffer_resident_mode"] = 1
            self.counters["point_buffer_preload_excluded_bytes"] = working_set_bytes
            self.events.append(
                TraceEvent(
                    0,
                    "point_buffer",
                    "resident_enable",
                    {
                        "working_set_bytes": working_set_bytes,
                        "capacity_bytes": self.config.point_buffer_capacity_bytes,
                        "preload_timed": False,
                    },
                )
            )
        else:
            self.counters["point_buffer_streaming_mode"] = 1

        self._np = None
        self._coord_np = None
        if self.config.functional_kernel in {"auto", "numpy"}:
            try:
                import numpy as np  # type: ignore
            except ImportError:
                if self.config.functional_kernel == "numpy":
                    raise RuntimeError(
                        "functional_kernel=numpy requires NumPy to be installed"
                    )
            else:
                self._np = np
                self._coord_np = np.asarray(
                    [point.as_tuple() for point in self.image.coordinates],
                    dtype=np.float32,
                )
                self.counters["functional_numpy_enabled"] = 1

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
        if stream not in self._dma_queues:
            raise ValueError(f"unknown DMA stream {stream}")
        tags: Set[int] = set()
        transaction = self.config.dram_transaction_bytes
        first_line = address // transaction
        last_line = (address + size - 1) // transaction
        ready_cycle = cycle + self.config.dma_command_cycles
        queue = self._dma_queues[stream]
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
            queue.append((ready_cycle, request))
            self._tag_owner[tag] = (chunk_index, phase)
            tags.add(tag)
        self.counters[f"{stream}_queued_transactions"] += len(tags)
        return tags

    def _schedule_load(
        self, task: FunctionalPointTask, chunk: FunctionalChunk, cycle: int
    ) -> None:
        if not self._resident_point_buffer:
            super()._schedule_load(task, chunk, cycle)
            return
        chunk.load_scheduled = True
        self._slot_owner[chunk.slot] = chunk.index
        ready_cycle = cycle + self.config.sram_read_latency
        self._local_load_ready[chunk.index] = ready_cycle
        bytes_read = chunk.point_count * self.config.point_bytes_per_point
        self.counters["chunks_load_scheduled"] += 1
        self.counters["point_buffer_read_commands"] += 1
        self.counters["point_buffer_bytes_read"] += bytes_read
        self.events.append(
            TraceEvent(
                cycle,
                "point_buffer",
                "read_request",
                {
                    "bucket": task.decision.bucket_id,
                    "chunk": chunk.index,
                    "slot": chunk.slot,
                    "bytes": bytes_read,
                    "ready_cycle": ready_cycle,
                },
            )
        )

    def _schedule_write(
        self, task: FunctionalPointTask, chunk: FunctionalChunk, cycle: int
    ) -> None:
        if not self._resident_point_buffer:
            super()._schedule_write(task, chunk, cycle)
            return
        chunk.write_scheduled = True
        ready_cycle = cycle + self.config.sram_write_latency
        self._local_write_ready[chunk.index] = ready_cycle
        bytes_written = chunk.point_count * self.config.dist_bytes_per_point
        self.counters["chunks_write_scheduled"] += 1
        self.counters["point_buffer_write_commands"] += 1
        self.counters["point_buffer_bytes_written"] += bytes_written
        self.events.append(
            TraceEvent(
                cycle,
                "point_buffer",
                "write_request",
                {
                    "bucket": task.decision.bucket_id,
                    "chunk": chunk.index,
                    "bytes": bytes_written,
                    "ready_cycle": ready_cycle,
                },
            )
        )

    def _service_local_point_buffer(self, cycle: int) -> None:
        if not self._resident_point_buffer or self.task is None:
            return
        for chunk_index, ready_cycle in list(self._local_load_ready.items()):
            if ready_cycle > cycle:
                continue
            chunk = self.task.chunks[chunk_index]
            chunk.loaded = True
            del self._local_load_ready[chunk_index]
            self.counters["point_buffer_read_completions"] += 1
            self.events.append(
                TraceEvent(
                    cycle,
                    "point_buffer",
                    "read_complete",
                    {"bucket": self.task.decision.bucket_id, "chunk": chunk_index},
                )
            )
        for chunk_index, ready_cycle in list(self._local_write_ready.items()):
            if ready_cycle > cycle:
                continue
            chunk = self.task.chunks[chunk_index]
            chunk.done = True
            self.task.completed_chunks += 1
            self._slot_owner[chunk.slot] = None
            del self._local_write_ready[chunk_index]
            self.counters["chunks_completed"] += 1
            self.counters["point_buffer_write_completions"] += 1
            self.events.append(
                TraceEvent(
                    cycle,
                    "point_buffer",
                    "write_complete",
                    {"bucket": self.task.decision.bucket_id, "chunk": chunk_index},
                )
            )

    def _handle_completions(
        self, cycle: int, completions: Iterable[MemoryCompletion]
    ) -> None:
        completion_list = list(completions)
        for completion in completion_list:
            if self._stream_outstanding[completion.stream] <= 0:
                raise RuntimeError(
                    f"completion without outstanding {completion.stream} DMA request"
                )
            self._stream_outstanding[completion.stream] -= 1
            self.counters[f"{completion.stream}_completed_transactions"] += 1
        super()._handle_completions(cycle, completion_list)

    def _submit_one(self, cycle: int, stream: str) -> bool:
        queue = self._dma_queues[stream]
        if not queue:
            return False
        ready_cycle, request = queue[0]
        if ready_cycle > cycle:
            return False
        if self._stream_outstanding[stream] >= self.config.dma_stream_outstanding:
            self.counters[f"{stream}_outstanding_stall_cycles"] += 1
            return False
        if not self.memory.can_accept(request) or not self.memory.submit(request):
            self.counters["dma_backpressure_cycles"] += 1
            self.counters[f"{stream}_memory_backpressure_cycles"] += 1
            return False
        queue.popleft()
        self._stream_outstanding[stream] += 1
        self.counters["dram_transactions"] += 1
        self.counters["dma_transactions"] += 1
        self.counters[f"{stream}_submitted_transactions"] += 1
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
        return True

    def _submit_dma(self, cycle: int) -> None:
        if self._resident_point_buffer:
            return
        submitted = 0
        idle_visits = 0
        stream_count = len(_DMA_STREAMS)
        while submitted < self.config.dma_channels and idle_visits < stream_count:
            if self.config.dma_arbiter == "priority":
                stream_index = idle_visits
            else:
                stream_index = self._dma_rr_cursor
                self._dma_rr_cursor = (self._dma_rr_cursor + 1) % stream_count
            stream = _DMA_STREAMS[stream_index]
            if self._submit_one(cycle, stream):
                submitted += 1
                idle_visits = 0
                self.counters["dma_arbiter_grants"] += 1
            else:
                idle_visits += 1
        if submitted:
            self.counters["dma_submit_active_cycles"] += 1
            self.counters["dma_submitted_this_cycle_max"] = max(
                self.counters["dma_submitted_this_cycle_max"], submitted
            )

    def _compute_chunk(
        self, task: FunctionalPointTask, chunk: FunctionalChunk
    ) -> None:
        if self._np is None or self._coord_np is None:
            super()._compute_chunk(task, chunk)
            self.counters["functional_scalar_chunks"] += 1
            return

        np = self._np
        start = task.bucket.point_ptr + chunk.point_offset
        stop = start + chunk.point_count
        references = task.decision.references
        if not references:
            raise RuntimeError("issued bucket has no distance references")
        coords = self._coord_np[start:stop]
        refs = np.asarray([point.as_tuple() for point in references], dtype=np.float32)
        dx = np.subtract(coords[:, None, 0], refs[None, :, 0], dtype=np.float32)
        dy = np.subtract(coords[:, None, 1], refs[None, :, 1], dtype=np.float32)
        dz = np.subtract(coords[:, None, 2], refs[None, :, 2], dtype=np.float32)
        xx = np.multiply(dx, dx, dtype=np.float32)
        yy = np.multiply(dy, dy, dtype=np.float32)
        zz = np.multiply(dz, dz, dtype=np.float32)
        distances = np.add(
            np.add(xx, yy, dtype=np.float32), zz, dtype=np.float32
        )
        reference_min = np.min(distances, axis=1)
        old = np.asarray(self.image.mdt[start:stop], dtype=np.float32)
        new = np.minimum(old, reference_min).astype(np.float32, copy=False)
        self.counters["functional_mdt_updates"] += int(np.count_nonzero(new != old))
        self.counters["functional_distance_evaluations"] += (
            chunk.point_count * len(references)
        )
        values = [f32(float(value)) for value in new.tolist()]
        self.image.mdt[start:stop] = values
        for offset, value in enumerate(values):
            point_index = start + offset
            if better(value, point_index, task.best_distance, task.best_index):
                task.best_distance = value
                task.best_index = point_index
        self.counters["functional_numpy_chunks"] += 1

    def step(self, cycle: int, completions: Iterable[MemoryCompletion]) -> None:
        self._handle_completions(cycle, completions)
        self._service_local_point_buffer(cycle)
        self._accept_task(cycle)
        self._fill_pingpong(cycle)
        self._advance_compute(cycle)
        self._finish_task(cycle)
        self._submit_dma(cycle)
        if self.task is not None:
            self.counters["point_engine_busy_cycles"] += 1
        queue_total = sum(len(queue) for queue in self._dma_queues.values())
        if queue_total:
            self.counters["dma_queue_nonempty_cycles"] += 1
        self.counters["dma_queue_max_occupancy"] = max(
            self.counters["dma_queue_max_occupancy"], queue_total
        )
        for stream, queue in self._dma_queues.items():
            self.counters[f"{stream}_queue_max_occupancy"] = max(
                self.counters[f"{stream}_queue_max_occupancy"], len(queue)
            )
            self.counters[f"{stream}_outstanding_max"] = max(
                self.counters[f"{stream}_outstanding_max"],
                self._stream_outstanding[stream],
            )
        if self._resident_point_buffer and (
            self._local_load_ready or self._local_write_ready
        ):
            self.counters["point_buffer_busy_cycles"] += 1

    def idle(self) -> bool:
        return (
            self.task is None
            and not self.bucket_fifo
            and not self.far_fifo
            and all(not queue for queue in self._dma_queues.values())
            and not self._tag_owner
            and not self._local_load_ready
            and not self._local_write_ready
        )


class OptimizedStrictClosedLoopQuickFPSCycleModel(
    strict_module.StrictClosedLoopQuickFPSCycleModel
):
    """Strict closed-loop model using the optimized Point-Engine memory path."""

    def run(self) -> SimulationResult:
        # ``StrictClosedLoopQuickFPSCycleModel`` resolves its point-engine class
        # from the module global.  Patch it only for the duration of this run and
        # serialize the operation so library callers remain deterministic.
        with _INSTALL_LOCK:
            previous = strict_module._FunctionalPointEngineSystem
            strict_module._FunctionalPointEngineSystem = (
                _OptimizedFunctionalPointEngineSystem
            )
            try:
                return super().run()
            finally:
                strict_module._FunctionalPointEngineSystem = previous
