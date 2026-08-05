from __future__ import annotations

from collections import Counter, deque
from typing import Deque, List, Tuple

from .closed_loop import (
    ClosedLoopDecision,
    ClosedLoopQuickFPSCycleModel,
    FarPointResult,
    _FunctionalPointEngineSystem,
)
from .memory import MemoryCompletion
from .model import SimulationResult, TraceEvent


class StrictClosedLoopQuickFPSCycleModel(ClosedLoopQuickFPSCycleModel):
    """Closed-loop simulator with explicit synchronous bucket SRAM stages.

    The base class closes the functional FPS loop. This public strict variant
    additionally models bucket-descriptor read latency before Bucket-CD and
    bucket-state write latency after FarPoint FIFO collection. Coordinate and
    MDT traffic continues to use the selected analytical or DRAMsim3 backend.
    """

    def run(self) -> SimulationResult:
        events: List[TraceEvent] = []
        counters: Counter[str] = Counter()
        point = _FunctionalPointEngineSystem(
            self.accelerator, self.image, self.memory, events, counters
        )
        sampled_indices = [self.first_sample]
        scheduler_name = "closed-loop-strict-pre-edge-sram"
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
                    "scheduler": scheduler_name,
                    "mode": "closed-loop",
                },
            )

        cycle = 0
        pending_completions: List[MemoryCompletion] = []
        iteration = 0
        current_sample = self.first_sample
        traversal = self._traversal_order(current_sample)
        traversal_index = 0

        fetch_pipeline: Deque[Tuple[int, int]] = deque()
        fetch_fifo: Deque[int] = deque()
        cd_pipeline: Deque[Tuple[int, ClosedLoopDecision]] = deque()
        decision_fifo: Deque[ClosedLoopDecision] = deque()
        writeback_pipeline: Deque[Tuple[int, FarPointResult]] = deque()

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
            cd_reserved_before = len(cd_pipeline) + len(decision_fifo)
            cd_input_ready_before = (
                cd_reserved_before < self.accelerator.bucket_decision_fifo_depth
            )
            fetched_head_before = fetch_fifo[0] if fetch_fifo else None
            fetch_ready_before = bool(
                fetch_pipeline
                and fetch_pipeline[0][0] <= cycle
                and len(fetch_fifo) < self.accelerator.bucket_decision_fifo_depth
            )
            decision_head_before = decision_fifo[0] if decision_fifo else None
            cd_ready_before = bool(cd_pipeline and cd_pipeline[0][0] <= cycle)
            writeback_ready_before = bool(
                writeback_pipeline and writeback_pipeline[0][0] <= cycle
            )
            bucket_ready_before = point.can_enqueue_bucket()
            far_available_before = point.far_available()

            point.step(cycle, pending_completions)
            pending_completions = []

            if writeback_ready_before:
                _, result = writeback_pipeline.popleft()
                self._apply_far_result(result, cycle, events)
                outstanding -= 1
                counters["bucket_completions"] += 1
                counters["bucket_buffer_write_commits"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_buffer",
                        "write_commit",
                        {
                            "bucket": result.bucket_id,
                            "far_index": result.far_index,
                            "far_distance": result.far_distance,
                        },
                    )
                )
                if outstanding < 0:
                    raise RuntimeError("more bucket completions than issues")

            if far_available_before:
                result = point.pop_far(cycle)
                ready_cycle = cycle + self.accelerator.sram_write_latency
                writeback_pipeline.append((ready_cycle, result))
                counters["bucket_buffer_write_requests"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_buffer",
                        "write_request",
                        {
                            "bucket": result.bucket_id,
                            "far_index": result.far_index,
                            "ready_cycle": ready_cycle,
                        },
                    )
                )

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
                fetched_head_before is not None
                and inject_cooldown == 0
                and cd_input_ready_before
            ):
                bucket_id = fetch_fifo.popleft()
                if bucket_id != fetched_head_before:
                    raise RuntimeError("bucket fetch FIFO head changed within a cycle")
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
                            "merge_count": decision.merge_count,
                            "far_to_sample": decision.far_to_sample,
                            "lower_bound": decision.lower_bound,
                        },
                    )
                )
            elif fetched_head_before is not None and inject_cooldown == 0:
                counters["bucket_decision_credit_stall_cycles"] += 1

            if fetch_ready_before:
                _, bucket_id = fetch_pipeline.popleft()
                fetch_fifo.append(bucket_id)
                counters["bucket_buffer_read_responses"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_buffer",
                        "read_response",
                        {"bucket": bucket_id},
                    )
                )

            fetch_reserved_before = len(fetch_pipeline) + len(fetch_fifo)
            if (
                traversal_index < len(traversal)
                and fetch_reserved_before < self.accelerator.bucket_decision_fifo_depth
            ):
                bucket_id = traversal[traversal_index]
                traversal_index += 1
                ready_cycle = cycle + self.accelerator.sram_read_latency
                fetch_pipeline.append((ready_cycle, bucket_id))
                counters["bucket_buffer_read_requests"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_buffer",
                        "read_request",
                        {"bucket": bucket_id, "ready_cycle": ready_cycle},
                    )
                )
            elif traversal_index < len(traversal):
                counters["bucket_buffer_read_stall_cycles"] += 1

            cd_reserved_after = len(cd_pipeline) + len(decision_fifo)
            counters["bucket_decision_fifo_max_occupancy"] = max(
                counters["bucket_decision_fifo_max_occupancy"], len(decision_fifo)
            )
            counters["bucket_reserved_credit_max"] = max(
                counters["bucket_reserved_credit_max"], cd_reserved_after
            )
            counters["bucket_fetch_max_occupancy"] = max(
                counters["bucket_fetch_max_occupancy"],
                len(fetch_pipeline) + len(fetch_fifo),
            )
            if cd_reserved_after > self.accelerator.bucket_decision_fifo_depth:
                raise RuntimeError("reserved bucket credits exceeded configured depth")

            scan_done = (
                traversal_index == len(traversal)
                and not fetch_pipeline
                and not fetch_fifo
                and not cd_pipeline
                and not decision_fifo
            )
            if (
                scan_done
                and outstanding == 0
                and not writeback_pipeline
                and point.idle()
                and self.memory.idle()
            ):
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
            if fetch_pipeline or fetch_fifo:
                counters["bucket_buffer_read_busy_cycles"] += 1
            if writeback_pipeline:
                counters["bucket_buffer_write_busy_cycles"] += 1
            counters["max_outstanding_buckets"] = max(
                counters["max_outstanding_buckets"], outstanding
            )
            cycle += 1
        else:
            raise TimeoutError(
                f"strict closed-loop QuickFPS exceeded {self.accelerator.max_cycles} cycles"
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
                "scheduler": scheduler_name,
                "mode": "closed-loop",
                "sample_count": self.sample_count,
                "first_sample": self.first_sample,
            },
        )
