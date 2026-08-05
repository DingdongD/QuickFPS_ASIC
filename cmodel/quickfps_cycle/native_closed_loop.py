from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List, Optional

from .batched_optimized_closed_loop import (
    _BatchedOptimizedFunctionalPointEngineSystem,
)
from .closed_loop import ClosedLoopDecision, ClosedLoopQuickFPSCycleModel
from .memory import MemoryCompletion
from .model import SimulationResult, TraceEvent
from .native_bucket_scheduler import NativeBucketScheduler


class _DiscardingEventList(list):
    def append(self, item) -> None:  # type: ignore[override,no-untyped-def]
        del item

    def extend(self, items) -> None:  # type: ignore[override,no-untyped-def]
        del items


class NativeStrictClosedLoopQuickFPSCycleModel(ClosedLoopQuickFPSCycleModel):
    """Closed-loop model with the strict Bucket-Engine scheduler in C++.

    The Python loop retains Point-Engine functional updates, DMA/Point-Buffer
    timing, DRAMsim3 clocking, and PTPX counters. Bucket SRAM requests,
    winner-first traversal, CD latency, FIFO credits, issue/defer/skip control,
    merge-buffer state, far writeback, and global reduction execute inside the
    native scheduler with the same pre-edge contract as the RTL-aligned Python
    reference.
    """

    def __init__(self, *args, native_scheduler_library: str | Path, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.native_scheduler_library = Path(native_scheduler_library).resolve()

    def run(self) -> SimulationResult:
        events: List[TraceEvent]
        events = [] if self.trace_events else _DiscardingEventList()
        counters: Counter[str] = Counter()
        point = _BatchedOptimizedFunctionalPointEngineSystem(
            self.accelerator, self.image, self.memory, events, counters
        )
        sampled_indices = [self.first_sample]
        scheduler_name = "native-cpp-closed-loop-strict-pre-edge-sram"

        if self.sample_count == 1:
            return SimulationResult(
                cycles=0,
                seconds=0.0,
                iterations=0,
                sampled_indices=sampled_indices,
                counters=dict(counters),
                memory_stats=dict(self.memory.stats()),
                events=events if self.trace_events else [],
                config={
                    "accelerator": self.accelerator.to_dict(),
                    "dram": self.dram.to_dict(),
                    "scheduler": scheduler_name,
                    "mode": "closed-loop",
                    "sample_count": self.sample_count,
                    "first_sample": self.first_sample,
                    "event_trace_materialized": self.trace_events,
                    "native_scheduler_library": str(self.native_scheduler_library),
                },
            )

        cycle = 0
        pending_completions: List[MemoryCompletion] = []
        native = NativeBucketScheduler(
            self.native_scheduler_library,
            self.image,
            self.accelerator,
            self.sample_count,
            self.first_sample,
        )
        try:
            while cycle < self.accelerator.max_cycles:
                bucket_ready_before = point.can_enqueue_bucket()
                far_available_before = point.far_available()

                point.step(cycle, pending_completions)
                pending_completions = []

                far_result = point.pop_far(cycle) if far_available_before else None
                external_idle = point.idle() and self.memory.idle()
                native_result = native.step(
                    cycle,
                    bucket_fifo_ready_before=bucket_ready_before,
                    external_idle_after_point_step=external_idle,
                    far_result=far_result,
                )

                if native_result.issue is not None:
                    issue = native_result.issue
                    references = tuple(
                        self.image.coordinates[index]
                        for index in issue.reference_indices
                    )
                    if len(references) != issue.merge_count + 1:
                        raise RuntimeError(
                            "native issue reference count does not match merge count"
                        )
                    decision = ClosedLoopDecision(
                        bucket_id=issue.bucket_id,
                        kind="issue",
                        merge_count=issue.merge_count,
                        sampled_index=issue.sampled_index,
                        sampled_point=self.image.coordinates[issue.sampled_index],
                        references=references,
                        forced_issue=issue.forced,
                    )
                    point.enqueue_bucket(decision, cycle)
                    events.append(
                        TraceEvent(
                            cycle,
                            "native_bucket_engine",
                            "issue",
                            {
                                "bucket": issue.bucket_id,
                                "sampled_index": issue.sampled_index,
                                "merge_count": issue.merge_count,
                                "reference_count": len(references),
                                "forced": issue.forced,
                            },
                        )
                    )

                if native_result.iteration_completed:
                    sampled_indices.append(native_result.next_sampled_index)
                    events.append(
                        TraceEvent(
                            cycle,
                            "native_bucket_engine",
                            "iteration_complete",
                            {
                                "iteration": native_result.completed_iteration,
                                "next_sampled_index": native_result.next_sampled_index,
                            },
                        )
                    )

                if native_result.simulation_done:
                    cycle += 1
                    break

                pending_completions = self.memory.tick()
                counters["cycles"] += 1
                cycle += 1
            else:
                raise TimeoutError(
                    f"native closed-loop QuickFPS exceeded "
                    f"{self.accelerator.max_cycles} cycles"
                )

            native.sync_image(self.image)
            for name, value in native.stats().items():
                counters[name] = value
        finally:
            native.close()

        if len(sampled_indices) != self.sample_count:
            raise RuntimeError(
                "native scheduler ended with an incomplete sampled sequence"
            )
        if counters["issued_buckets"] != counters["bucket_completions"]:
            raise RuntimeError(
                "native scheduler ended with unmatched issue/completion counts"
            )

        return SimulationResult(
            cycles=cycle,
            seconds=cycle / self.accelerator.clock_hz,
            iterations=self.sample_count - 1,
            sampled_indices=sampled_indices,
            counters=dict(counters),
            memory_stats=dict(self.memory.stats()),
            events=events if self.trace_events else [],
            config={
                "accelerator": self.accelerator.to_dict(),
                "dram": self.dram.to_dict(),
                "scheduler": scheduler_name,
                "mode": "closed-loop",
                "sample_count": self.sample_count,
                "first_sample": self.first_sample,
                "event_trace_materialized": self.trace_events,
                "native_scheduler_library": str(self.native_scheduler_library),
                "native_event_scope": "Point-Engine and iteration boundaries",
            },
        )
