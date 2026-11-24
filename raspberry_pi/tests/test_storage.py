"""Tests for serial measurement and event logs."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from smartplant_pi.storage import EventLogger, MeasurementCsvLogger


class StorageTests(unittest.TestCase):
    def test_event_logger(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events_log.txt"
            logger = EventLogger(path)
            logger.log_measurement(
                {"run_id": "run-1", "mode": "BASELINE", "uptime_ms": 20000,
                 "triggered_rules": [1, 3]}, "serial:/dev/serial0"
            )
            logger.log_event("camera_capture", status="success")
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(["measurement", "alert", "alert", "camera_capture"],
                             [e["event_type"] for e in events])
            self.assertEqual([1, 3], [events[1]["rule_id"], events[2]["rule_id"]])

    def test_csv_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "measurements.csv"
            logger = MeasurementCsvLogger(path)
            payload = {"run_id": "run-1", "protocol": "smart-plant-serial-v1",
                       "mode": "BASELINE", "sequence": 1, "uptime_ms": 20000,
                       "sampling_interval_ms": 20000, "triggered_rules": []}
            logger.log(payload, "2026-01-01T00:00:00+00:00")
            logger.log({**payload, "sequence": 2}, "2026-01-01T00:00:20+00:00")
            with path.open(newline="") as fp:
                rows = list(csv.DictReader(fp))
            self.assertEqual(["1", "2"], [row["sequence"] for row in rows])


if __name__ == "__main__":
    unittest.main()
