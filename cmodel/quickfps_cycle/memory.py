from __future__ import annotations

import ctypes
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple

from .config import DramConfig


@dataclass(frozen=True)
class MemoryRequest:
    tag: int
    address: int
    size: int
    is_write: bool
    stream: str
    submitted_cycle: int


@dataclass(frozen=True)
class MemoryCompletion:
    tag: int
    address: int
    is_write: bool
    stream: str
    submitted_cycle: int
    completed_cycle: int

    @property
    def latency(self) -> int:
        return self.completed_cycle - self.submitted_cycle


class MemoryBackend(Protocol):
    cycle: int

    def can_accept(self, request: MemoryRequest) -> bool: ...
    def submit(self, request: MemoryRequest) -> bool: ...
    def tick(self) -> List[MemoryCompletion]: ...
    def idle(self) -> bool: ...
    def stats(self) -> Dict[str, int]: ...


@dataclass
class _BankState:
    available_cycle: int = 0
    open_row: Optional[int] = None


class _StreamActivity:
    def __init__(self) -> None:
        self.outstanding: Counter[str] = Counter()
        self.busy_cycles: Counter[str] = Counter()
        self.dma_busy_cycles = 0

    def accepted(self, stream: str) -> None:
        self.outstanding[stream] += 1

    def complete(self, stream: str) -> None:
        if self.outstanding[stream] <= 0:
            raise RuntimeError(f"completion without outstanding {stream} request")
        self.outstanding[stream] -= 1

    def tick(self) -> None:
        any_busy = False
        for stream, count in self.outstanding.items():
            if count > 0:
                self.busy_cycles[stream] += 1
                any_busy = True
        if any_busy:
            self.dma_busy_cycles += 1

    def stats(self) -> Dict[str, int]:
        value = {
            f"{stream}_busy_cycles": cycles
            for stream, cycles in self.busy_cycles.items()
        }
        value["dma_busy_cycles"] = self.dma_busy_cycles
        value["max_streams"] = sum(1 for count in self.outstanding.values() if count > 0)
        return value


class BankedDramModel:
    """Deterministic cycle model with channel/bank/row state.

    It preserves queue capacity, bank conflicts, row hits, activation and
    precharge cost, burst occupancy, independent channels, and per-stream
    reader/writer activity windows used by the PTPX energy adapter.
    """

    def __init__(self, config: DramConfig):
        config.validate()
        self.config = config
        self.cycle = 0
        self._pending: List[Tuple[int, MemoryRequest]] = []
        self._banks = [
            _BankState()
            for _ in range(config.channels * config.banks_per_channel)
        ]
        self._activity = _StreamActivity()
        self.accepted = 0
        self.completed = 0
        self.row_hits = 0
        self.row_misses = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self.latency_sum = 0
        self.latency_max = 0

    def _decode(self, address: int) -> Tuple[int, int, int]:
        burst = address // self.config.burst_bytes
        bank = burst % self.config.banks_per_channel
        channel = (burst // self.config.banks_per_channel) % self.config.channels
        row = address // self.config.row_bytes
        return channel, bank, row

    def can_accept(self, request: MemoryRequest) -> bool:
        del request
        return len(self._pending) < self.config.queue_depth

    def submit(self, request: MemoryRequest) -> bool:
        if request.size <= 0:
            raise ValueError("memory request size must be positive")
        if not self.can_accept(request):
            return False
        channel, bank, row = self._decode(request.address)
        bank_index = channel * self.config.banks_per_channel + bank
        state = self._banks[bank_index]
        start = max(self.cycle, state.available_cycle)
        if state.open_row == row:
            command_latency = self.config.t_cl
            self.row_hits += 1
        else:
            command_latency = self.config.t_rcd + self.config.t_cl
            if state.open_row is not None:
                command_latency += self.config.t_rp
            state.open_row = row
            self.row_misses += 1
        beats = math.ceil(request.size / self.config.burst_bytes)
        transfer = max(self.config.t_burst, beats * self.config.t_burst)
        ready = start + command_latency + transfer
        if request.is_write:
            ready += self.config.write_recovery
            self.bytes_written += request.size
        else:
            self.bytes_read += request.size
        state.available_cycle = ready
        self._pending.append((ready, request))
        self._activity.accepted(request.stream)
        self.accepted += 1
        return True

    def tick(self) -> List[MemoryCompletion]:
        self._activity.tick()
        self.cycle += 1
        ready_items = [item for item in self._pending if item[0] <= self.cycle]
        self._pending = [item for item in self._pending if item[0] > self.cycle]
        ready_items.sort(key=lambda item: (item[0], item[1].tag))
        completions = []
        for _, request in ready_items:
            completion = MemoryCompletion(
                tag=request.tag,
                address=request.address,
                is_write=request.is_write,
                stream=request.stream,
                submitted_cycle=request.submitted_cycle,
                completed_cycle=self.cycle,
            )
            self._activity.complete(request.stream)
            self.latency_sum += completion.latency
            self.latency_max = max(self.latency_max, completion.latency)
            completions.append(completion)
        self.completed += len(completions)
        return completions

    def idle(self) -> bool:
        return not self._pending

    def stats(self) -> Dict[str, int]:
        value = {
            "accepted": self.accepted,
            "completed": self.completed,
            "row_hits": self.row_hits,
            "row_misses": self.row_misses,
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "latency_sum": self.latency_sum,
            "latency_max": self.latency_max,
        }
        value.update(self._activity.stats())
        return value


class DramSim3Backend:
    """ctypes wrapper around ``libquickfps_dramsim3_bridge.so``.

    The bridge links the official pinned ``umd-memsys/DRAMsim3`` repository.
    The Python side submits exactly one request per configured DRAM transaction
    and tracks the activity window of each QuickFPS DMA stream.
    """

    def __init__(
        self,
        library: str | Path,
        config_file: str | Path,
        output_dir: str | Path,
    ):
        self._lib = ctypes.CDLL(str(library))
        self._configure_api()
        self._handle = self._lib.qfps_dramsim3_create(
            str(config_file).encode(), str(output_dir).encode()
        )
        if not self._handle:
            raise RuntimeError("failed to create DRAMsim3 backend")
        self.cycle = 0
        self._requests: Dict[int, MemoryRequest] = {}
        self._activity = _StreamActivity()
        self.accepted = 0
        self.completed = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self.latency_sum = 0
        self.latency_max = 0

    def _configure_api(self) -> None:
        self._lib.qfps_dramsim3_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.qfps_dramsim3_create.restype = ctypes.c_void_p
        self._lib.qfps_dramsim3_destroy.argtypes = [ctypes.c_void_p]
        self._lib.qfps_dramsim3_will_accept.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_int,
        ]
        self._lib.qfps_dramsim3_will_accept.restype = ctypes.c_int
        self._lib.qfps_dramsim3_add.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_int,
            ctypes.c_uint64,
        ]
        self._lib.qfps_dramsim3_add.restype = ctypes.c_int
        self._lib.qfps_dramsim3_tick.argtypes = [ctypes.c_void_p]
        self._lib.qfps_dramsim3_poll.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.qfps_dramsim3_poll.restype = ctypes.c_int

    def can_accept(self, request: MemoryRequest) -> bool:
        return bool(
            self._lib.qfps_dramsim3_will_accept(
                self._handle, request.address, int(request.is_write)
            )
        )

    def submit(self, request: MemoryRequest) -> bool:
        if request.tag in self._requests:
            raise ValueError(f"duplicate DRAM request tag {request.tag}")
        accepted = bool(
            self._lib.qfps_dramsim3_add(
                self._handle,
                request.address,
                int(request.is_write),
                request.tag,
            )
        )
        if accepted:
            self._requests[request.tag] = request
            self._activity.accepted(request.stream)
            self.accepted += 1
            if request.is_write:
                self.bytes_written += request.size
            else:
                self.bytes_read += request.size
        return accepted

    def tick(self) -> List[MemoryCompletion]:
        self._activity.tick()
        self._lib.qfps_dramsim3_tick(self._handle)
        self.cycle += 1
        completions: List[MemoryCompletion] = []
        while True:
            tag = ctypes.c_uint64()
            address = ctypes.c_uint64()
            is_write = ctypes.c_int()
            if not self._lib.qfps_dramsim3_poll(
                self._handle,
                ctypes.byref(tag),
                ctypes.byref(address),
                ctypes.byref(is_write),
            ):
                break
            request = self._requests.pop(int(tag.value), None)
            if request is None:
                raise RuntimeError(f"DRAMsim3 returned unknown tag {int(tag.value)}")
            completion = MemoryCompletion(
                tag=request.tag,
                address=int(address.value),
                is_write=bool(is_write.value),
                stream=request.stream,
                submitted_cycle=request.submitted_cycle,
                completed_cycle=self.cycle,
            )
            self._activity.complete(request.stream)
            self.latency_sum += completion.latency
            self.latency_max = max(self.latency_max, completion.latency)
            completions.append(completion)
        self.completed += len(completions)
        return completions

    def idle(self) -> bool:
        return not self._requests

    def stats(self) -> Dict[str, int]:
        value = {
            "accepted": self.accepted,
            "completed": self.completed,
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "latency_sum": self.latency_sum,
            "latency_max": self.latency_max,
        }
        value.update(self._activity.stats())
        return value

    def close(self) -> None:
        if getattr(self, "_handle", None):
            self._lib.qfps_dramsim3_destroy(self._handle)
            self._handle = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
