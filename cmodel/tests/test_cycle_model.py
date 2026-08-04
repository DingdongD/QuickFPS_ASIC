from __future__ import annotations

import unittest

from quickfps_cycle.config import AcceleratorConfig, DramConfig
from quickfps_cycle.memory import BankedDramModel, MemoryRequest
from quickfps_cycle.model import QuickFPSCycleModel, _PointEngineSystem
from quickfps_cycle.workload import synthetic_workload


class PointEngineTimingTest(unittest.TestCase):
    def test_existing_48_point_latency(self) -> None:
        config = AcceleratorConfig()
        self.assertEqual(
            _PointEngineSystem.rtl_point_engine_latency(48, 3, config), 38
        )

    def test_partial_batch_increases_by_one_batch(self) -> None:
        config = AcceleratorConfig()
        latency8 = _PointEngineSystem.rtl_point_engine_latency(8, 0, config)
        latency9 = _PointEngineSystem.rtl_point_engine_latency(9, 0, config)
        self.assertEqual(latency9, latency8 + 1)


class DramTimingTest(unittest.TestCase):
    def test_row_hit_is_faster_than_closed_row(self) -> None:
        config = DramConfig(channels=1, banks_per_channel=1, queue_depth=8)
        dram = BankedDramModel(config)
        first = MemoryRequest(1, 0x0000, 64, False, "read", 0)
        self.assertTrue(dram.submit(first))
        while dram.completed < 1:
            dram.tick()
        first_done = dram.cycle
        second = MemoryRequest(2, 0x0040, 64, False, "read", dram.cycle)
        self.assertTrue(dram.submit(second))
        while dram.completed < 2:
            dram.tick()
        second_latency = dram.cycle - first_done
        self.assertLess(second_latency, config.t_rcd + config.t_cl + config.t_burst)
        self.assertEqual(dram.row_hits, 1)
        self.assertEqual(dram.row_misses, 1)


class SystemTimingTest(unittest.TestCase):
    def test_pingpong_dma_system_completes(self) -> None:
        workload = synthetic_workload([300, 129, 17], iterations=2, issue_all=True)
        accelerator = AcceleratorConfig(
            chunk_points=128,
            bucket_fifo_depth=2,
            far_fifo_depth=2,
            max_cycles=2_000_000,
        )
        result = QuickFPSCycleModel(workload, accelerator=accelerator).run()
        self.assertGreater(result.cycles, 0)
        self.assertEqual(result.counters["issued_buckets"], 6)
        self.assertEqual(result.counters["bucket_completions"], 6)
        self.assertEqual(result.counters["iterations_completed"], 2)
        self.assertEqual(result.counters["chunks_completed"], 12)
        self.assertGreater(result.counters["dma_transactions"], 0)
        self.assertEqual(result.memory_stats["accepted"], result.memory_stats["completed"])


if __name__ == "__main__":
    unittest.main()
