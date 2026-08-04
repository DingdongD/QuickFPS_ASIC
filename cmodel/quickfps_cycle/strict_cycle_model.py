from __future__ import annotations

from collections import Counter, deque
from typing import Deque, List, Optional, Tuple

from .config import AcceleratorConfig, DramConfig
from .memory import BankedDramModel, MemoryBackend, MemoryCompletion
from .model import SimulationResult, TraceEvent, _PointEngineSystem
from .workload import BucketAction, IterationWork, Workload


class StrictQuickFPSCycleModel:
    """Edge-accurate QuickFPS system scheduler.

    This scheduler follows the pre-edge semantics of ``bucket_decision_pipe``.
    In particular, ``in_ready`` is derived from the reserved-credit count that
    exists *before* the active clock edge.  If the decision FIFO is full and its
    head is consumed on an edge, a new input cannot be accepted on that same
    edge; the freed credit is visible during the following cycle.  This detail
    matters when comparing long backpressure traces cycle by cycle.
    """

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
        cd_pipeline: Deque[Tuple[int, BucketAction]] = deque()
        decision_fifo: Deque[BucketAction] = deque()
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
                    "scheduler": "strict-pre-edge",
                },
            )

        current: IterationWork = self.workload.iterations[0]
        sampled_indices.append(current.sampled_index)
        events.append(
            TraceEvent(0, "bucket_engine", "iteration_start", {"iteration": 0})
        )

        while cycle < self.accelerator.max_cycles:
            # Capture all combinational predicates from the pre-edge state.
            reserved_before = len(cd_pipeline) + len(decision_fifo)
            input_ready_before = (
                reserved_before < self.accelerator.bucket_decision_fifo_depth
            )
            decision_head_before = decision_fifo[0] if decision_fifo else None
            cd_ready_before = bool(cd_pipeline and cd_pipeline[0][0] <= cycle)

            point.step(cycle, pending_completions)
            pending_completions = []

            completed_bucket = point.pop_far(cycle)
            if completed_bucket is not None:
                outstanding -= 1
                counters["bucket_completions"] += 1
                if outstanding < 0:
                    raise RuntimeError("more bucket completions than issues")

            # Registered FIFO read. The decision selected above is the one that
            # was visible before this edge; a CD output written below cannot be
            # consumed until the next cycle.
            if decision_head_before is not None:
                action = decision_head_before
                if action.kind == "issue":
                    if point.can_enqueue_bucket():
                        popped = decision_fifo.popleft()
                        if popped is not action:
                            raise RuntimeError("decision FIFO head changed within a cycle")
                        point.enqueue_bucket(action, cycle)
                        outstanding += 1
                        counters["issued_buckets"] += 1
                        events.append(
                            TraceEvent(
                                cycle,
                                "bucket_engine",
                                "issue",
                                {
                                    "bucket": action.bucket_id,
                                    "outstanding": outstanding,
                                },
                            )
                        )
                    else:
                        counters["bucket_fifo_backpressure_cycles"] += 1
                        counters["decision_fifo_head_stall_cycles"] += 1
                else:
                    popped = decision_fifo.popleft()
                    if popped is not action:
                        raise RuntimeError("decision FIFO head changed within a cycle")
                    counters[f"{action.kind}_buckets"] += 1
                    events.append(
                        TraceEvent(
                            cycle,
                            "bucket_engine",
                            action.kind,
                            {"bucket": action.bucket_id},
                        )
                    )

            # CD output write uses the pre-edge output-valid predicate. Reserved
            # credit admission guarantees room even if no decision was popped.
            if cd_ready_before:
                _, action = cd_pipeline.popleft()
                if len(decision_fifo) >= self.accelerator.bucket_decision_fifo_depth:
                    raise RuntimeError("bucket decision FIFO credit invariant failed")
                decision_fifo.append(action)
                counters["bucket_decision_fifo_pushes"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_decision_fifo",
                        "push",
                        {"bucket": action.bucket_id, "kind": action.kind},
                    )
                )

            # Input acceptance is based on pre-edge in_ready. A simultaneous
            # FIFO pop does not retroactively make this edge ready.
            if inject_cooldown > 0:
                inject_cooldown -= 1
            if (
                action_index < len(current.actions)
                and inject_cooldown == 0
                and input_ready_before
            ):
                action = current.actions[action_index]
                action_index += 1
                cd_pipeline.append(
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
            elif (
                action_index < len(current.actions)
                and inject_cooldown == 0
                and not input_ready_before
            ):
                counters["bucket_decision_credit_stall_cycles"] += 1
                events.append(
                    TraceEvent(
                        cycle,
                        "bucket_cd",
                        "credit_stall",
                        {"reserved": reserved_before},
                    )
                )

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
                action_index == len(current.actions)
                and not cd_pipeline
                and not decision_fifo
            )
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
            if cd_pipeline or decision_fifo:
                counters["bucket_pipeline_active_cycles"] += 1
            counters["max_outstanding_buckets"] = max(
                counters["max_outstanding_buckets"], outstanding
            )
            cycle += 1
        else:
            raise TimeoutError(
                f"QuickFPS cycle model exceeded {self.accelerator.max_cycles} cycles"
            )

        memory_stats = self.memory.stats()
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
                "scheduler": "strict-pre-edge",
            },
        )
