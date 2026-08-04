from __future__ import annotations

from collections import Counter, deque
from typing import Deque, List, Optional, Tuple

from .config import AcceleratorConfig, DramConfig
from .memory import BankedDramModel, MemoryBackend, MemoryCompletion
from .model import SimulationResult, TraceEvent, _PointEngineSystem
from .workload import BucketAction, IterationWork, Workload


class QuickFPSCycleModel:
    """Cycle-accurate system scheduler for QuickFPS.

    The bucket front end mirrors ``bucket_decision_pipe.v``: accepted entries
    reserve one of ``bucket_decision_fifo_depth`` credits, spend four cycles in
    ``bucket_cd``, enter a registered decision FIFO, and are consumed at II=1
    when the downstream bucket FIFO is ready. Point, ping-pong, DMA, and DRAM
    timing are delegated to the RTL-calibrated ``_PointEngineSystem``.
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
                },
            )

        current: IterationWork = self.workload.iterations[0]
        sampled_indices.append(current.sampled_index)
        events.append(
            TraceEvent(0, "bucket_engine", "iteration_start", {"iteration": 0})
        )

        while cycle < self.accelerator.max_cycles:
            # Memory responses from the prior ClockTick are visible at this
            # cycle's beginning, matching synchronous RTL handshakes.
            point.step(cycle, pending_completions)
            pending_completions = []

            # FarPoint FIFO has one read port; collect at most one bucket result
            # per cycle.
            completed_bucket = point.pop_far(cycle)
            if completed_bucket is not None:
                outstanding -= 1
                counters["bucket_completions"] += 1
                if outstanding < 0:
                    raise RuntimeError("more bucket completions than issues")

            # Consume an entry already resident in the decision FIFO. Entries
            # written by bucket_cd below are first visible next cycle, matching
            # the registered sync_fifo implementation.
            if decision_fifo:
                action = decision_fifo[0]
                if action.kind == "issue":
                    if point.can_enqueue_bucket():
                        decision_fifo.popleft()
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
                    decision_fifo.popleft()
                    counters[f"{action.kind}_buckets"] += 1
                    events.append(
                        TraceEvent(
                            cycle,
                            "bucket_engine",
                            action.kind,
                            {"bucket": action.bucket_id},
                        )
                    )

            # Retire at most one bucket_cd result per cycle into the decision
            # FIFO. Reserved-credit admission guarantees this cannot overflow.
            if cd_pipeline and cd_pipeline[0][0] <= cycle:
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

            # RTL in_ready is driven by total reserved credits, including both
            # in-flight CD entries and decisions waiting for downstream space.
            reserved = len(cd_pipeline) + len(decision_fifo)
            if inject_cooldown > 0:
                inject_cooldown -= 1
            if (
                action_index < len(current.actions)
                and inject_cooldown == 0
                and reserved < self.accelerator.bucket_decision_fifo_depth
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
            elif action_index < len(current.actions) and reserved >= self.accelerator.bucket_decision_fifo_depth:
                counters["bucket_decision_credit_stall_cycles"] += 1

            counters["bucket_decision_fifo_max_occupancy"] = max(
                counters["bucket_decision_fifo_max_occupancy"], len(decision_fifo)
            )
            counters["bucket_reserved_credit_max"] = max(
                counters["bucket_reserved_credit_max"],
                len(cd_pipeline) + len(decision_fifo),
            )

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
            },
        )
