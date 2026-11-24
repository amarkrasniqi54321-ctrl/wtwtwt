"""Event and sensor measurement logging for the Raspberry Pi runner."""

from __future__ import annotations

from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import threading
from typing import Any


class EventLogger:
    """Write the measurements and events received by the Pi over UART."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.last_measurement_received_at: str | None = None

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")

    def log_measurement(self, payload: dict[str, Any], peer: str) -> str:
        received_at = datetime.now(timezone.utc).isoformat()
        measurement = {
            "event_type": "measurement",
            "received_at": received_at,
            "peer": peer,
            **payload,
        }
        self._append(measurement)
        for rule_id in payload["triggered_rules"]:
            alert = {
                "event_type": "alert",
                "received_at": received_at,
                "rule_id": rule_id,
                "source_uptime_ms": payload["uptime_ms"],
            }
            for optional_field in ("device_id", "run_id", "mode"):
                if optional_field in payload:
                    alert[optional_field] = payload[optional_field]
            self._append(alert)
        self.last_measurement_received_at = received_at
        return received_at

    def log_event(self, event_type: str, **fields: Any) -> str:
        """Append a timestamped non-measurement experiment event."""
        if not event_type or "event_type" in fields or "received_at" in fields:
            raise ValueError("invalid event fields")
        received_at = datetime.now(timezone.utc).isoformat()
        self._append(
            {
                "event_type": event_type,
                "received_at": received_at,
                **fields,
            }
        )
        return received_at


class MeasurementCsvLogger:
    """Append every real serial measurement to a stable CSV schema."""

    FIELDNAMES = [
        "received_at",
        "run_id",
        "protocol",
        "mode",
        "sequence",
        "uptime_ms",
        "sampling_interval_ms",
        "air_valid",
        "air_temperature_c",
        "air_humidity_percent",
        "air_error",
        "soil_raw_valid",
        "soil_raw",
        "soil_millivolts",
        "soil_valid",
        "soil_humidity_normalized",
        "soil_error",
        "triggered_rules",
    ]

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def log(self, payload: dict[str, Any], received_at: str) -> None:
        row = {
            name: payload.get(name) for name in self.FIELDNAMES
        }
        row["received_at"] = received_at
        row["triggered_rules"] = ";".join(
            str(rule_id) for rule_id in payload.get("triggered_rules", [])
        )
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_header = not self.path.exists() or self.path.stat().st_size == 0
            with self.path.open("a", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=self.FIELDNAMES)
                if write_header:
                    writer.writeheader()
                writer.writerow(row)
