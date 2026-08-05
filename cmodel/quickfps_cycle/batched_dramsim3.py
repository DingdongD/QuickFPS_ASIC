from __future__ import annotations

import ctypes
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

from .dramsim3_clock import read_dramsim3_tck_ns
from .memory import DramSim3Backend, MemoryCompletion, MemoryRequest


class BatchedDramSim3Backend(DramSim3Backend):
    """DRAMsim3 backend with batched C-ABI submission and completion polling."""

    _POLL_CAPACITY = 256

    def _configure_api(self) -> None:
        super()._configure_api()
        self._lib.qfps_dramsim3_add_batch.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_uint64,
        ]
        self._lib.qfps_dramsim3_add_batch.restype = ctypes.c_uint64
        self._lib.qfps_dramsim3_poll_batch.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_uint64,
        ]
        self._lib.qfps_dramsim3_poll_batch.restype = ctypes.c_uint64

    def submit_many(self, requests: Sequence[MemoryRequest]) -> int:
        if not requests:
            return 0
        for request in requests:
            if request.tag in self._requests:
                raise ValueError(f"duplicate DRAM request tag {request.tag}")
        count = len(requests)
        addresses = (ctypes.c_uint64 * count)(
            *(request.address for request in requests)
        )
        writes = (ctypes.c_int * count)(
            *(int(request.is_write) for request in requests)
        )
        tags = (ctypes.c_uint64 * count)(*(request.tag for request in requests))
        accepted = int(
            self._lib.qfps_dramsim3_add_batch(
                self._handle, addresses, writes, tags, count
            )
        )
        if accepted < 0 or accepted > count:
            raise RuntimeError(f"invalid DRAMsim3 batch acceptance count {accepted}")
        for request in requests[:accepted]:
            self._requests[request.tag] = request
            self._activity.accepted(request.stream)
            self.accepted += 1
            if request.is_write:
                self.bytes_written += request.size
            else:
                self.bytes_read += request.size
        return accepted

    def submit(self, request: MemoryRequest) -> bool:
        return self.submit_many([request]) == 1

    def tick(self) -> List[MemoryCompletion]:
        self._activity.tick()
        self._lib.qfps_dramsim3_tick(self._handle)
        self.cycle += 1
        completions: List[MemoryCompletion] = []
        capacity = self._POLL_CAPACITY
        while True:
            tags = (ctypes.c_uint64 * capacity)()
            addresses = (ctypes.c_uint64 * capacity)()
            writes = (ctypes.c_int * capacity)()
            count = int(
                self._lib.qfps_dramsim3_poll_batch(
                    self._handle, tags, addresses, writes, capacity
                )
            )
            if count < 0 or count > capacity:
                raise RuntimeError(f"invalid DRAMsim3 poll count {count}")
            for index in range(count):
                tag = int(tags[index])
                request = self._requests.pop(tag, None)
                if request is None:
                    raise RuntimeError(f"DRAMsim3 returned unknown tag {tag}")
                completion = MemoryCompletion(
                    tag=request.tag,
                    address=int(addresses[index]),
                    is_write=bool(writes[index]),
                    stream=request.stream,
                    submitted_cycle=request.submitted_cycle,
                    completed_cycle=self.cycle,
                )
                self._activity.complete(request.stream)
                self.latency_sum += completion.latency
                self.latency_max = max(self.latency_max, completion.latency)
                completions.append(completion)
            if count < capacity:
                break
        self.completed += len(completions)
        return completions


class ClockScaledBatchedDramSim3Backend:
    """Batched DRAMsim3 exposed in accelerator-cycle time."""

    def __init__(
        self,
        library: str | Path,
        config_file: str | Path,
        output_dir: str | Path,
        accelerator_clock_hz: int,
    ):
        if accelerator_clock_hz <= 0:
            raise ValueError("accelerator_clock_hz must be positive")
        self._inner = BatchedDramSim3Backend(library, config_file, output_dir)
        self._accelerator_period_ns = 1.0e9 / float(accelerator_clock_hz)
        self._dram_tck_ns = read_dramsim3_tck_ns(config_file)
        self._time_credit_ns = 0.0
        self._requests: Dict[int, MemoryRequest] = {}
        self._stream_outstanding: Counter[str] = Counter()
        self._stream_busy_cycles: Counter[str] = Counter()
        self.cycle = 0
        self.dram_clock_ticks = 0
        self.accepted = 0
        self.completed = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self.latency_sum = 0
        self.latency_max = 0
        self.dma_busy_cycles = 0
        self.batch_submit_calls = 0
        self.batch_poll_cycles = 0

    @property
    def dram_tck_ns(self) -> float:
        return self._dram_tck_ns

    def can_accept(self, request: MemoryRequest) -> bool:
        return self._inner.can_accept(request)

    def _register_requests(self, requests: Sequence[MemoryRequest]) -> None:
        for request in requests:
            self._requests[request.tag] = request
            self._stream_outstanding[request.stream] += 1
            self.accepted += 1
            if request.is_write:
                self.bytes_written += request.size
            else:
                self.bytes_read += request.size

    def submit_many(self, requests: Sequence[MemoryRequest]) -> int:
        for request in requests:
            if request.tag in self._requests:
                raise ValueError(f"duplicate DRAM request tag {request.tag}")
        accepted = self._inner.submit_many(requests)
        self._register_requests(requests[:accepted])
        self.batch_submit_calls += 1
        return accepted

    def submit(self, request: MemoryRequest) -> bool:
        return self.submit_many([request]) == 1

    def _record_activity_cycle(self) -> None:
        any_busy = False
        for stream, count in self._stream_outstanding.items():
            if count > 0:
                self._stream_busy_cycles[stream] += 1
                any_busy = True
        if any_busy:
            self.dma_busy_cycles += 1

    def tick(self) -> List[MemoryCompletion]:
        self._record_activity_cycle()
        self._time_credit_ns += self._accelerator_period_ns
        raw_completions: List[MemoryCompletion] = []
        epsilon = 1.0e-12
        while self._time_credit_ns + epsilon >= self._dram_tck_ns:
            raw_completions.extend(self._inner.tick())
            self._time_credit_ns -= self._dram_tck_ns
            self.dram_clock_ticks += 1

        self.cycle += 1
        if raw_completions:
            self.batch_poll_cycles += 1
        completions: List[MemoryCompletion] = []
        for raw in raw_completions:
            request = self._requests.pop(raw.tag, None)
            if request is None:
                raise RuntimeError(f"DRAMsim3 returned unknown tag {raw.tag}")
            if self._stream_outstanding[request.stream] <= 0:
                raise RuntimeError(
                    f"DRAMsim3 completion without outstanding {request.stream} request"
                )
            self._stream_outstanding[request.stream] -= 1
            completion = MemoryCompletion(
                tag=request.tag,
                address=raw.address,
                is_write=raw.is_write,
                stream=request.stream,
                submitted_cycle=request.submitted_cycle,
                completed_cycle=self.cycle,
            )
            self.latency_sum += completion.latency
            self.latency_max = max(self.latency_max, completion.latency)
            self.completed += 1
            completions.append(completion)
        return completions

    def idle(self) -> bool:
        return not self._requests and self._inner.idle()

    def stats(self) -> Dict[str, int]:
        value = {
            "accepted": self.accepted,
            "completed": self.completed,
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "latency_sum": self.latency_sum,
            "latency_max": self.latency_max,
            "dma_busy_cycles": self.dma_busy_cycles,
            "dram_clock_ticks": self.dram_clock_ticks,
            "accelerator_cycles": self.cycle,
            "dram_tck_fs": int(round(self._dram_tck_ns * 1.0e6)),
            "dramsim3_batch_submit_calls": self.batch_submit_calls,
            "dramsim3_batch_completion_cycles": self.batch_poll_cycles,
        }
        value.update(
            {
                f"{stream}_busy_cycles": cycles
                for stream, cycles in self._stream_busy_cycles.items()
            }
        )
        return value

    def close(self) -> None:
        self._inner.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
