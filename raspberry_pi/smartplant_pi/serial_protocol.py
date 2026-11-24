"""Validation for the ESP32 GPIO UART JSON-lines measurement protocol."""

from __future__ import annotations

import json
import math
from typing import Any


SERIAL_PREFIX = "SMARTPLANT_JSON:"
PROTOCOL_VERSION = "smart-plant-serial-v1"
OPERATING_MODES = {"BASELINE", "OPTIMIZED"}
BASELINE_SAMPLING_INTERVAL_MS = 20000
UART_BAUD_RATE = 115200
DEFAULT_SERIAL_DEVICE = "/dev/serial0"
ESP32_UART_TX_GPIO = 17
ESP32_UART_RX_GPIO = 16


class SerialProtocolError(ValueError):
    """Raised when a prefixed serial record is malformed or inconsistent."""


def _boolean(data: dict[str, Any], name: str) -> bool:
    value = data.get(name)
    if not isinstance(value, bool):
        raise SerialProtocolError(f"{name} must be a boolean")
    return value


def _integer(data: dict[str, Any], name: str, minimum: int) -> int:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SerialProtocolError(f"{name} must be an integer >= {minimum}")
    return value


def _optional_number(
    data: dict[str, Any], name: str, minimum: float, maximum: float
) -> float | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SerialProtocolError(f"{name} must be a number or null")
    try:
        result = float(value)
    except OverflowError as error:
        raise SerialProtocolError(f"{name} is outside numeric range") from error
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise SerialProtocolError(f"{name} is outside [{minimum}, {maximum}]")
    return result


def _optional_error(data: dict[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is not None and (not isinstance(value, str) or not value or len(value) > 64):
        raise SerialProtocolError(f"{name} must be null or a short string")
    return value


def validate_serial_measurement(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SerialProtocolError("serial JSON must be an object")
    if data.get("protocol") != PROTOCOL_VERSION:
        raise SerialProtocolError("unsupported serial protocol")
    mode = data.get("mode")
    if not isinstance(mode, str) or mode not in OPERATING_MODES:
        raise SerialProtocolError("mode must be BASELINE or OPTIMIZED")

    sequence = _integer(data, "sequence", 1)
    uptime_ms = _integer(data, "uptime_ms", 0)
    sampling_interval_ms = _integer(
        data, "sampling_interval_ms", 10000 if mode == "OPTIMIZED" else BASELINE_SAMPLING_INTERVAL_MS
    )
    if (
        mode == "BASELINE"
        and sampling_interval_ms != BASELINE_SAMPLING_INTERVAL_MS
    ):
        raise SerialProtocolError(
            "BASELINE sampling interval must be "
            f"{BASELINE_SAMPLING_INTERVAL_MS} ms"
        )

    air_valid = _boolean(data, "air_valid")
    temperature = _optional_number(data, "air_temperature_c", -40, 80)
    humidity = _optional_number(data, "air_humidity_percent", 0, 100)
    air_error = _optional_error(data, "air_error")
    if (air_valid and (temperature is None or humidity is None)) or (not air_valid and (temperature is not None or humidity is not None)):
        raise SerialProtocolError("air validity does not match air values")
    if air_valid and air_error is not None:
        raise SerialProtocolError("valid air reading cannot contain air_error")
    if not air_valid and air_error is None:
        raise SerialProtocolError("invalid air reading must contain air_error")

    soil_raw_valid = _boolean(data, "soil_raw_valid")
    soil_raw = _optional_number(data, "soil_raw", 0, 4095)
    soil_millivolts = _optional_number(data, "soil_millivolts", 0, 3300)
    soil_valid = _boolean(data, "soil_valid")
    soil_normalized = _optional_number(
        data, "soil_humidity_normalized", 0, 1000
    )
    soil_error = _optional_error(data, "soil_error")
    if soil_raw_valid != (soil_raw is not None):
        raise SerialProtocolError("soil_raw_valid does not match soil_raw")
    if soil_millivolts is not None and not soil_raw_valid:
        raise SerialProtocolError("soil millivolts require a valid raw reading")
    if soil_valid != (soil_normalized is not None):
        raise SerialProtocolError("soil validity does not match normalized value")
    if soil_valid and not soil_raw_valid:
        raise SerialProtocolError("normalized soil value requires a raw reading")
    if soil_valid and soil_error is not None:
        raise SerialProtocolError("valid normalized soil reading cannot contain soil_error")
    if not soil_raw_valid and soil_error is None:
        raise SerialProtocolError("invalid soil reading must contain soil_error")
    if soil_raw_valid and not soil_valid and soil_error != "calibration_required":
        raise SerialProtocolError(
            "uncalibrated raw soil reading must report calibration_required"
        )

    triggered = data.get("triggered_rules")
    if not isinstance(triggered, list) or any(
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10
        for value in triggered
    ):
        raise SerialProtocolError("triggered_rules must contain ids from 1 to 10")
    if len(triggered) != len(set(triggered)):
        raise SerialProtocolError("triggered_rules contains duplicates")

    return {
        "protocol": PROTOCOL_VERSION,
        "mode": mode,
        "sequence": sequence,
        "uptime_ms": uptime_ms,
        "sampling_interval_ms": sampling_interval_ms,
        "air_valid": air_valid,
        "air_temperature_c": temperature,
        "air_humidity_percent": humidity,
        "air_error": air_error,
        "soil_raw_valid": soil_raw_valid,
        "soil_raw": int(soil_raw) if soil_raw is not None else None,
        "soil_millivolts": (
            int(soil_millivolts) if soil_millivolts is not None else None
        ),
        "soil_valid": soil_valid,
        "soil_humidity_normalized": (
            int(soil_normalized) if soil_normalized is not None else None
        ),
        "soil_error": soil_error,
        "triggered_rules": triggered,
    }


def parse_serial_line(line: bytes | str) -> dict[str, Any] | None:
    """Return a validated measurement, or None for ordinary ESP-IDF log lines."""
    if isinstance(line, bytes):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SerialProtocolError("prefixed serial line is not UTF-8") from error
    else:
        text = line
    text = text.strip()
    if not text.startswith(SERIAL_PREFIX):
        return None
    try:
        data = json.loads(text[len(SERIAL_PREFIX) :])
    except json.JSONDecodeError as error:
        raise SerialProtocolError(f"invalid serial JSON: {error.msg}") from error
    return validate_serial_measurement(data)
