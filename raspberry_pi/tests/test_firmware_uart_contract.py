from pathlib import Path
import re
import unittest

from smartplant_pi.serial_protocol import (
    BASELINE_SAMPLING_INTERVAL_MS,
    ESP32_UART_RX_GPIO,
    ESP32_UART_TX_GPIO,
    PROTOCOL_VERSION,
    SERIAL_PREFIX,
    UART_BAUD_RATE,
)


WORKSPACE = Path(__file__).resolve().parents[2]
ESP32_MAIN = WORKSPACE / "esp32" / "main"
HEADER = ESP32_MAIN / "measurement_output.h"
SOURCE = ESP32_MAIN / "measurement_output.c"
MAIN = ESP32_MAIN / "main.c"
WAKE = ESP32_MAIN / "raspberry_pi_wake.c"


@unittest.skipUnless(HEADER.is_file(), "ESP32 firmware source is not deployed on this host")
class FirmwareUartContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.wake = WAKE.read_text(encoding="utf-8")

    def test_c_and_python_protocol_constants_match(self) -> None:
        self.assertRegex(
            self.header,
            rf'#define\s+SMART_PLANT_SERIAL_PREFIX\s+"{re.escape(SERIAL_PREFIX)}"',
        )
        self.assertRegex(
            self.header,
            rf'#define\s+SMART_PLANT_SERIAL_PROTOCOL\s+"{re.escape(PROTOCOL_VERSION)}"',
        )
        self.assertRegex(
            self.header,
            rf"#define\s+SMART_PLANT_UART_BAUD_RATE\s+{UART_BAUD_RATE}\b",
        )
        self.assertRegex(
            self.header,
            rf"#define\s+SMART_PLANT_BASELINE_INTERVAL_MS\s+{BASELINE_SAMPLING_INTERVAL_MS}U\b",
        )

    def test_machine_stream_is_uart2_gpio17_gpio16_8n1(self) -> None:
        self.assertIn("#define SMART_PLANT_UART_PORT UART_NUM_2", self.header)
        self.assertIn(
            f"#define SMART_PLANT_UART_TX_GPIO GPIO_NUM_{ESP32_UART_TX_GPIO}",
            self.header,
        )
        self.assertIn(
            f"#define SMART_PLANT_UART_RX_GPIO GPIO_NUM_{ESP32_UART_RX_GPIO}",
            self.header,
        )
        for setting in (
            ".data_bits = UART_DATA_8_BITS",
            ".parity = UART_PARITY_DISABLE",
            ".stop_bits = UART_STOP_BITS_1",
            ".flow_ctrl = UART_HW_FLOWCTRL_DISABLE",
            "uart_set_pin(SMART_PLANT_UART_PORT",
            "uart_write_bytes(SMART_PLANT_UART_PORT",
        ):
            self.assertIn(setting, self.source)

    def test_console_cannot_be_configured_on_machine_uart(self) -> None:
        self.assertIn("#if CONFIG_ESP_CONSOLE_UART_NUM == 2", self.source)
        self.assertIn("the human-readable console must use UART0", self.source)

    def test_baseline_transmits_each_cycle_at_20000_ms(self) -> None:
        self.assertIn("const uint32_t next_interval_ms = SMART_PLANT_BASELINE_INTERVAL_MS", self.main)
        loop = self.main[self.main.index("while (true)") :]
        self.assertLess(loop.index("read_air(&sample)"), loop.index("read_soil(&sample)"))
        self.assertLess(
            loop.index("read_soil(&sample)"),
            loop.index("measurement_output_write(&output)"),
        )

    def test_formatter_uses_exact_prefix_and_protocol(self) -> None:
        self.assertIn("SMART_PLANT_SERIAL_PREFIX", self.source)
        self.assertIn("SMART_PLANT_SERIAL_PROTOCOL", self.source)
        self.assertIn('strcmp(record->mode, "BASELINE")', self.source)
        self.assertIn("SMART_PLANT_BASELINE_INTERVAL_MS", self.source)

    def test_optimized_wake_uses_retained_cycle_deep_sleep_state(self) -> None:
        self.assertIn("RTC_DATA_ATTR static optimized_rtc_state_t", self.main)
        self.assertIn("esp_sleep_get_wakeup_cause()", self.main)
        self.assertIn("optimized_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER", self.main)
        self.assertIn("esp_sleep_enable_timer_wakeup", self.main)
        self.assertIn("esp_deep_sleep_start", self.main)
        self.assertIn("CONFIG_SMART_PLANT_OPTIMIZED_PI_WAKE_CYCLES", self.main)
        self.assertIn("camera_policy_step(", self.main)
        self.assertIn("camera_policy_complete(", self.main)
        self.assertIn("optimized_restore_rule_state(&ruleset)", self.main)
        self.assertIn("optimized_save_rule_state(&ruleset)", self.main)
        self.assertIn("optimized_save_measurement(&output)", self.main)
        self.assertNotIn("esp_reset_reason() != ESP_RST_DEEPSLEEP", self.main)
        self.assertIn("GPIO_MODE_OUTPUT_OD", self.wake)
        self.assertIn("RASPBERRY_PI_WAKE_PULSE_MS", self.wake)
        self.assertIn("CONFIG_SMART_PLANT_PI_WAKE_COOLDOWN_S", self.wake)

    def test_console_mirrors_identical_machine_record_before_sleep(self):
        self.assertIn("fwrite(line, 1, length, stdout)", self.source)
        self.assertIn("fflush(stdout)", self.source)
        self.assertLess(self.main.index("measurement_output_write(&output)"),
                        self.main.index("optimized_enter_deep_sleep();", self.main.index("measurement_output_write(&output)")))


if __name__ == "__main__":
    unittest.main()
