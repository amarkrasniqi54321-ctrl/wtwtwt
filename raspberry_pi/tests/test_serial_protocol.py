import json
import unittest

from smartplant_pi.serial_protocol import (
    SERIAL_PREFIX,
    SerialProtocolError,
    parse_serial_line,
)


def valid_payload() -> dict:
    return {
        "protocol": "smart-plant-serial-v1",
        "mode": "BASELINE",
        "sequence": 7,
        "uptime_ms": 140000,
        "sampling_interval_ms": 20000,
        "air_valid": False,
        "air_temperature_c": None,
        "air_humidity_percent": None,
        "air_error": "ESP_ERR_TIMEOUT",
        "soil_raw_valid": True,
        "soil_raw": 904,
        "soil_millivolts": 876,
        "soil_valid": False,
        "soil_humidity_normalized": None,
        "soil_error": "calibration_required",
        "triggered_rules": [],
    }


class SerialProtocolTests(unittest.TestCase):
    def test_ordinary_idf_log_is_ignored(self) -> None:
        self.assertIsNone(parse_serial_line("I (123) smart_plant: ready"))

    def test_valid_invalid_sensor_record_is_preserved(self) -> None:
        record = parse_serial_line(
            SERIAL_PREFIX + json.dumps(valid_payload(), separators=(",", ":"))
        )
        self.assertEqual(904, record["soil_raw"])
        self.assertFalse(record["air_valid"])
        self.assertIsNone(record["air_temperature_c"])

    def test_exact_machine_line_with_real_readings_is_accepted(self) -> None:
        payload = valid_payload()
        payload.update(
            {
                "air_valid": True,
                "air_temperature_c": 22.9,
                "air_humidity_percent": 73.0,
                "air_error": None,
                "soil_raw": 2204,
                "soil_millivolts": 1924,
                "triggered_rules": [1],
            }
        )
        line = SERIAL_PREFIX + json.dumps(payload, separators=(",", ":"))
        record = parse_serial_line(line)
        self.assertEqual("smart-plant-serial-v1", record["protocol"])
        self.assertEqual("BASELINE", record["mode"])
        self.assertEqual(20000, record["sampling_interval_ms"])
        self.assertEqual(22.9, record["air_temperature_c"])
        self.assertEqual(2204, record["soil_raw"])
        self.assertEqual([1], record["triggered_rules"])

    def test_baseline_interval_cannot_drift(self) -> None:
        payload = valid_payload()
        payload["sampling_interval_ms"] = 4000
        with self.assertRaisesRegex(SerialProtocolError, "20000"):
            parse_serial_line(SERIAL_PREFIX + json.dumps(payload))

    def test_prefixed_invalid_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(SerialProtocolError, "invalid serial JSON"):
            parse_serial_line(SERIAL_PREFIX + "{not-json}")

    def test_validity_must_match_values(self) -> None:
        payload = valid_payload()
        payload["air_valid"] = True
        with self.assertRaisesRegex(SerialProtocolError, "validity"):
            parse_serial_line(SERIAL_PREFIX + json.dumps(payload))

    def test_malformed_mode_is_protocol_error(self):
        payload = valid_payload()
        payload["mode"] = []
        with self.assertRaises(SerialProtocolError):
            parse_serial_line(SERIAL_PREFIX + json.dumps(payload))

    def test_partial_invalid_air_reading_is_rejected(self):
        payload = valid_payload()
        payload["air_temperature_c"] = 22
        with self.assertRaises(SerialProtocolError):
            parse_serial_line(SERIAL_PREFIX + json.dumps(payload))

    def test_optimized_configured_ten_second_interval_is_accepted(self):
        payload = valid_payload()
        payload.update(mode="OPTIMIZED", sampling_interval_ms=10000)
        self.assertEqual(10000, parse_serial_line(SERIAL_PREFIX + json.dumps(payload))["sampling_interval_ms"])

    def test_overflowing_sensor_number_is_protocol_error(self):
        payload = valid_payload()
        payload["soil_raw"] = 10 ** 400
        with self.assertRaises(SerialProtocolError):
            parse_serial_line(SERIAL_PREFIX + json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
