from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quickfps_cycle.config import AcceleratorConfig
from quickfps_cycle.dramsim3_clock import read_dramsim3_tck_ns
from quickfps_cycle.strict_cycle_model import StrictQuickFPSCycleModel
from quickfps_cycle.workload import synthetic_workload


class StrictBucketCreditTest(unittest.TestCase):
    def test_full_credit_pop_is_visible_one_cycle_later(self) -> None:
        workload = synthetic_workload([32] * 8, iterations=1, issue_all=True)
        config = AcceleratorConfig(
            bucket_cd_latency=4,
            bucket_issue_ii=1,
            bucket_decision_fifo_depth=4,
            bucket_fifo_depth=1,
            far_fifo_depth=1,
            chunk_points=32,
            max_cycles=1_000_000,
        )
        result = StrictQuickFPSCycleModel(workload, accelerator=config).run()
        accepts = [
            event.cycle
            for event in result.events
            if event.component == "bucket_cd" and event.event == "accept"
        ]
        self.assertGreaterEqual(len(accepts), 5)
        self.assertEqual(accepts[:4], [0, 1, 2, 3])
        # At cycle 5 the full decision-credit set pops one output, but RTL
        # in_ready was low before that edge. The next input is accepted at 6.
        self.assertEqual(accepts[4], 6)
        self.assertGreater(result.counters["bucket_decision_credit_stall_cycles"], 0)
        self.assertLessEqual(result.counters["bucket_reserved_credit_max"], 4)
        self.assertEqual(result.counters["issued_buckets"], 8)
        self.assertEqual(result.counters["bucket_completions"], 8)
        self.assertEqual(result.config["scheduler"], "strict-pre-edge")


class DramClockConfigTest(unittest.TestCase):
    def test_read_tck_from_dramsim3_ini(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.ini"
            path.write_text("[timing]\ntCK = 0.833\ntCL = 17\n")
            self.assertAlmostEqual(read_dramsim3_tck_ns(path), 0.833)

    def test_missing_tck_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.ini"
            path.write_text("[timing]\ntCL = 17\n")
            with self.assertRaises(ValueError):
                read_dramsim3_tck_ns(path)


if __name__ == "__main__":
    unittest.main()
