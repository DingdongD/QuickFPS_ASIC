from __future__ import annotations

from collections import Counter
from typing import List, Sequence, Tuple

from . import closed_loop_strict as strict_module
from .closed_loop import FunctionalChunk, FunctionalPointTask
from .memory import MemoryRequest
from .model import SimulationResult, TraceEvent
from .optimized_closed_loop import (
    _DMA_STREAMS,
    _INSTALL_LOCK,
    _OptimizedFunctionalPointEngineSystem,
)


class _BatchedOptimizedFunctionalPointEngineSystem(
    _OptimizedFunctionalPointEngineSystem
):
    """Use one C-ABI call per accelerator cycle for ready DRAM transactions."""

    def _schedule_load(
        self, task: FunctionalPointTask, chunk: FunctionalChunk, cycle: int
    ) -> None:
        if not self._resident_point_buffer:
            self.counters["coord_read_bytes_requested"] += (
                chunk.point_count * self.config.coord_bytes_per_point
            )
            self.counters["dist_read_bytes_requested"] += (
                chunk.point_count * self.config.dist_bytes_per_point
            )
        super()._schedule_load(task, chunk, cycle)

    def _schedule_write(
        self, task: FunctionalPointTask, chunk: FunctionalChunk, cycle: int
    ) -> None:
        if not self._resident_point_buffer:
            self.counters["dist_write_bytes_requested"] += (
                chunk.point_count * self.config.dist_bytes_per_point
            )
        super()._schedule_write(task, chunk, cycle)

    def _select_batch(self, cycle: int) -> List[Tuple[str, MemoryRequest]]:
        selected: List[Tuple[str, MemoryRequest]] = []
        offsets: Counter[str] = Counter()
        temporary_outstanding = Counter(self._stream_outstanding)
        stream_count = len(_DMA_STREAMS)
        idle_visits = 0
        cursor = self._dma_rr_cursor

        while len(selected) < self.config.dma_channels and idle_visits < stream_count:
            if self.config.dma_arbiter == "priority":
                stream_index = idle_visits
            else:
                stream_index = cursor
                cursor = (cursor + 1) % stream_count
            stream = _DMA_STREAMS[stream_index]
            queue = self._dma_queues[stream]
            offset = offsets[stream]
            eligible = False
            if offset < len(queue):
                ready_cycle, request = queue[offset]
                eligible = (
                    ready_cycle <= cycle
                    and temporary_outstanding[stream]
                    < self.config.dma_stream_outstanding
                )
                if eligible:
                    selected.append((stream, request))
                    offsets[stream] += 1
                    temporary_outstanding[stream] += 1
                    idle_visits = 0
            if not eligible:
                if (
                    offset < len(queue)
                    and queue[offset][0] <= cycle
                    and temporary_outstanding[stream]
                    >= self.config.dma_stream_outstanding
                ):
                    self.counters[f"{stream}_outstanding_stall_cycles"] += 1
                idle_visits += 1

        if self.config.dma_arbiter == "round_robin":
            self._dma_rr_cursor = cursor
        return selected

    def _commit_batch(
        self,
        cycle: int,
        selected: Sequence[Tuple[str, MemoryRequest]],
        accepted: int,
    ) -> None:
        if accepted < 0 or accepted > len(selected):
            raise RuntimeError(f"invalid memory batch acceptance count {accepted}")
        for stream, request in selected[:accepted]:
            ready_cycle, queued = self._dma_queues[stream].popleft()
            del ready_cycle
            if queued.tag != request.tag:
                raise RuntimeError("DMA stream queue changed during batch submission")
            self._stream_outstanding[stream] += 1
            self.counters["dram_transactions"] += 1
            self.counters["dma_transactions"] += 1
            self.counters[f"{stream}_submitted_transactions"] += 1
            self.counters["dma_arbiter_grants"] += 1
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
                        "batched": True,
                    },
                )
            )
        if accepted:
            self.counters["dma_submit_active_cycles"] += 1
            self.counters["dma_submitted_this_cycle_max"] = max(
                self.counters["dma_submitted_this_cycle_max"], accepted
            )
            self.counters["dma_batch_submit_calls"] += 1
            self.counters["dma_batch_transactions"] += accepted
        if accepted < len(selected):
            self.counters["dma_backpressure_cycles"] += 1
            self.counters["dma_batch_partial_accepts"] += 1

    def _submit_dma(self, cycle: int) -> None:
        if self._resident_point_buffer:
            return
        submit_many = getattr(self.memory, "submit_many", None)
        if not callable(submit_many):
            super()._submit_dma(cycle)
            return
        selected = self._select_batch(cycle)
        if not selected:
            return
        accepted = int(submit_many([request for _, request in selected]))
        self._commit_batch(cycle, selected, accepted)


class BatchedOptimizedStrictClosedLoopQuickFPSCycleModel(
    strict_module.StrictClosedLoopQuickFPSCycleModel
):
    """Strict closed-loop model with resident SRAM and batched DRAMsim3 I/O."""

    def run(self) -> SimulationResult:
        with _INSTALL_LOCK:
            previous = strict_module._FunctionalPointEngineSystem
            strict_module._FunctionalPointEngineSystem = (
                _BatchedOptimizedFunctionalPointEngineSystem
            )
            try:
                return super().run()
            finally:
                strict_module._FunctionalPointEngineSystem = previous
