from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .memory import DramSim3Backend, MemoryCompletion, MemoryRequest


_TCK_RE = re.compile(
    r"^\s*tCK\s*=\s*([0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)\s*$",
    re.MULTILINE,
)


def read_dramsim3_tck_ns(config_file: str | Path) -> float:
    """Read the DRAM clock period in nanoseconds from a DRAMsim3 INI file."""
    path = Path(config_file)
    match = _TCK_RE.search(path.read_text(errors="replace"))
    if not match:
        raise ValueError(f"DRAMsim3 config does not define tCK: {path}")
    value = float(match.group(1))
    if value <= 0.0:
        raise ValueError(f"DRAMsim3 tCK must be positive, got {value}")
    return value


class ClockScaledDramSim3Backend:
    """Expose DRAMsim3 in accelerator-cycle time.

    DRAMsim3's ``ClockTick`` advances one memory clock, whereas one invocation
    of the QuickFPS C-model represents one accelerator clock.  For DDR4-2400
    and a 1 GHz accelerator this ratio is not one.  A fractional accumulator
    advances the correct number of DRAM ticks per accelerator cycle and
    translates completions and activity windows back into accelerator cycles.
    """

    def __init__(
        self,
        library: str | Path,
        config_file: str | Path,
        output_dir: str | Path,
        accelerator_clock_hz: int,
    ):
        if accelerator_clock_hz <= 0:
            raise ValueError("accelerator_clock_hz must be positive")
        self._inner = DramSim3Backend(library, config_file, output_dir)
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

    @property
    def dram_tck_ns(self) -> float:
        return self._dram_tck_ns

    def can_accept(self, request: MemoryRequest) -> bool:
        return self._inner.can_accept(request)

    def submit(self, request: MemoryRequest) -> bool:
        if request.tag in self._requests:
            raise ValueError(f"duplicate DRAM request tag {request.tag}")
        accepted = self._inner.submit(request)
        if accepted:
            self._requests[request.tag] = request
            self._stream_outstanding[request.stream] += 1
            self.accepted += 1
            if request.is_write:
                self.bytes_written += request.size
            else:
                self.bytes_read += request.size
        return accepted

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
        raw_completions = []
        epsilon = 1.0e-12
        while self._time_credit_ns + epsilon >= self._dram_tck_ns:
            raw_completions.extend(self._inner.tick())
            self._time_credit_ns -= self._dram_tck_ns
            self.dram_clock_ticks += 1

        self.cycle += 1
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
