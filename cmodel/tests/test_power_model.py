from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quickfps_cycle.power import PTPXEnergyModel


class PTPXEnergyModelTest(unittest.TestCase):
    def test_two_reader_instances_use_independent_busy_windows(self) -> None:
        payload = {
            "modules": {
                "axi_burst_reader": {
                    "active_pj_per_cycle": 2.0,
                    "idle_pj_per_cycle": 0.1,
                    "counters": [
                        "coord_read_busy_cycles",
                        "dist_read_busy_cycles",
                    ],
                    "instances": 2,
                },
                "axi_burst_writer": {
                    "active_pj_per_cycle": 3.0,
                    "idle_pj_per_cycle": 0.2,
                    "counters": ["dist_write_busy_cycles"],
                },
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "energy.json"
            path.write_text(json.dumps(payload))
            model = PTPXEnergyModel.load(path)
        estimate = model.estimate(
            {
                "coord_read_busy_cycles": 40,
                "dist_read_busy_cycles": 20,
                "dist_write_busy_cycles": 25,
            },
            total_cycles=100,
        )
        # Readers: 60 active instance-cycles and 140 idle instance-cycles.
        self.assertAlmostEqual(estimate["axi_burst_reader_pj"], 60 * 2.0 + 140 * 0.1)
        # Writer: 25 active cycles and 75 idle cycles.
        self.assertAlmostEqual(estimate["axi_burst_writer_pj"], 25 * 3.0 + 75 * 0.2)
        self.assertAlmostEqual(
            estimate["total_pj"],
            estimate["axi_burst_reader_pj"] + estimate["axi_burst_writer_pj"],
        )

    def test_event_mode_uses_event_count(self) -> None:
        payload = {
            "modules": {
                "dma_command": {
                    "active_pj_per_cycle": 0.0,
                    "idle_pj_per_cycle": 0.01,
                    "event_pj": 4.5,
                    "counter_mode": "event",
                    "counters": ["dma_commands"],
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "energy.json"
            path.write_text(json.dumps(payload))
            model = PTPXEnergyModel.load(path)
        estimate = model.estimate({"dma_commands": 10}, total_cycles=100)
        self.assertAlmostEqual(estimate["dma_command_pj"], 10 * 4.5 + 100 * 0.01)


if __name__ == "__main__":
    unittest.main()
