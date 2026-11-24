# Wiring: ESP32, sensors, buzzer, UART and Raspberry Pi wake

Target: ESP32-WROOM-32 38-pin development board. Disconnect USB power before
changing wiring. Disconnect Pi power as well before altering inter-board wiring. Printed labels and the exact module datasheet take precedence
over assumed pin order.

## Raspberry Pi wake and optimized poweroff

- ESP32 GPIO26 -> Raspberry Pi GPIO3, physical pin 5.
- ESP32 GND -> Raspberry Pi GND, physical pin 6.
- GPIO26 uses direct-wire open-drain logic: released HIGH/floating, asserted
  LOW for 250 ms. Do not add a 3.3 V drive to the Pi wake input.
- Never connect Raspberry Pi physical pins 2 or 4 (5 V) to an ESP32 GPIO.
- Raspberry Pi 4 EEPROM must have `WAKE_ON_GPIO=1`.
- Do not enable `dtoverlay=gpio-shutdown`; with the lab direct wire it can turn
  an intended wake pulse into a shutdown request while the Pi is running.
- Keep the Pi supply connected after `systemctl poweroff`. GPIO3 wake does not
  work if Pi power is physically removed.
- Direct wiring can spuriously wake the Pi if ESP32 loses power. The lab's
  optional NPN-transistor circuit is required to prevent that electrical edge
  case; its inverted firmware must not be used with the current direct wire.

Before an autonomous experiment, verify the actual board and bootloader rather
than assuming every Raspberry Pi supports this method:

```sh
tr -d '\0' </proc/device-tree/model
sudo rpi-eeprom-config | grep -E '^(WAKE_ON_GPIO|POWER_OFF_ON_HALT)='
grep -n '^[[:space:]]*dtoverlay=gpio-shutdown' /boot/firmware/config.txt || true
```

For the verified Raspberry Pi 4 Model B setup, `WAKE_ON_GPIO=1` and
`POWER_OFF_ON_HALT=0` are required. The latter keeps the GPIO wake circuitry
powered after `systemctl poweroff`. A red power LED alone is not evidence that
GPIO3 wake is configured; test one actual halt-and-wake cycle before recording
an energy experiment.

## Connection table

| Device | Device pin | ESP32 | Notes |
|---|---|---|---|
| Passive buzzer module | `S`, `SIG` or `IN` | GPIO25 / D25 | 2 kHz LEDC signal |
| Passive buzzer module | `+` / `VCC` | 3V3 | Only for a 3.3-V-compatible module |
| Passive buzzer module | `-` / `GND` | GND | Common ground |
| DHT11 | `DATA`, `OUT` or `S` | GPIO4 / D4 | Bidirectional single-wire data |
| DHT11 | `VCC` / `+` | 3V3 | Do not pull DATA up to 5 V |
| DHT11 | `GND` / `-` | GND | Common ground |
| Soil sensor | `AO`, `AOUT` or analog `S` | GPIO34 / D34 | ADC1 channel 6; do not use digital `DO` |
| Soil sensor | `VCC` | 3V3 | Use only if the module supports 3.3 V |
| Soil sensor | `GND` | GND | Common ground |
| ESP32 UART2 TX | GPIO17 | Pi GPIO15 RX, physical pin 10 | Measurement JSON to Pi |
| ESP32 UART2 RX | GPIO16 | Pi GPIO14 TX, physical pin 8 | Configured for future Pi-to-ESP32 data |
| ESP32 Pi wake | GPIO26 | Pi GPIO3, physical pin 5 | Open-drain 250 ms LOW pulse at 90 or 360 deep-sleep cycles, or immediately on new alarm |
| ESP32 GND | GND | Pi GND, physical pin 6 | Required common UART reference |

## Conflict and electrical checks

- GPIO25, GPIO4, GPIO34, GPIO17, GPIO16 and GPIO26 are distinct, so the
  assignments do not conflict.
- GPIO34 is input-only and has no internal pull-up or pull-down. This is correct
  for the soil sensor's analog output.
- GPIO34 uses ADC1 channel 6. ADC2/Wi-Fi contention is therefore avoided if
  Wi-Fi is added later.
- The voltage on GPIO34 must stay within the ESP32 input range and must never
  exceed 3.3 V. Verify the sensor module's AO range with its datasheet or a
  multimeter before connection.
- All module grounds must connect to the same ESP32 GND.
- Breadboard power rails may be split in the middle; verify continuity.

## Raspberry Pi wake signal

GPIO26 is configured as `GPIO_MODE_OUTPUT_OD` and released at every ESP32
boot. The firmware pulls Pi GPIO3 (physical pin 5) LOW for 250 ms when the adaptive policy requests a wake, then releases the line. Open-drain release means the ESP32
never actively drives the Pi signal HIGH. The Pi GPIO3 pull-up holds the
released level; do not add a pull-up to 5 V.

The ESP32 records its cycle counter in RTC memory, calls
`esp_sleep_enable_timer_wakeup()` for the twenty-second interval, and enters
`esp_deep_sleep_start()` after each measurement. Timer wakeups retain the
counter and policy state; cold and unexpected resets discard them. A newly detected alarm can request a wake immediately. Repeated sensor alarms are suppressed by the retained policy state during timer sleep; an unexpected reset discards that state and can cause a new request.

Connect ESP32 GND to Raspberry Pi physical pin 6. If the existing UART ground
already uses physical pin 6, that is the required common reference; do not
connect an additional power wire between the boards.

## DHT11 pull-up

The driver enables GPIO4's internal pull-up. A bare four-pin DHT11 should also
have a 4.7-10 kOhm resistor between DATA and 3V3. Many three-pin breakout modules
already include it, but verify the board. Use an external pull-up if readings
time out or checksums are unreliable. Never connect this pull-up to 5 V.

## Soil sensor notes

Use the analog output, not the adjustable digital comparator output. A
capacitive 3.3-V sensor is preferable for long-term use. Resistive probes
corrode when powered continuously.

A disconnected GPIO34 can float to an apparently plausible value, so software
cannot prove connection in every case. The driver rejects ADC rail saturation,
excessively unstable sample groups and ADC errors, but physical inspection is
still required.

Do not treat raw ADC values as universal moisture percentages. Each sensor,
soil type, supply and probe position requires its own dry/wet calibration as
described in [LAB_RUNBOOK.md](../../docs/LAB_RUNBOOK.md).

## Safe bring-up order

1. Disconnect USB and inspect every connection.
2. Check that 3V3 and GND are not shorted.
3. Connect USB and open ESP-IDF Monitor.
4. Confirm there is no startup beep.
5. Confirm actual DHT11 readings or diagnose its explicit timeout/checksum log.
6. Observe raw GPIO34 ADC readings with soil calibration disabled.
7. Measure dry and wet references, configure them, rebuild and flash.
8. Only then verify normalized soil values and the `< 300` dry-soil alert.

A successful build does not prove correct wiring or sensor accuracy.

## Raspberry Pi GPIO UART and Monsoon

The measurement protocol uses ESP32 UART2 at 115200 baud, 8N1. It does not use
the ESP-IDF USB/UART0 console. On Raspberry Pi, disable the serial login console,
enable the serial hardware, reboot, and verify `/dev/serial0`. The Pi receiver
uses that device by default. The identical measurement JSON is also mirrored to the USB/UART0 console for evidence when Pi is halted.

TX and RX must be crossed exactly as shown above. Both boards use 3.3 V UART
logic. Never connect a 5 V UART signal, Pi 5 V, or Pi 3.3 V to these signal
connections. The three-wire UART connection itself supplies no power.

For a Monsoon measurement, keep the UART common ground but ensure that USB or
another supply cannot also power/backfeed the ESP32. Use the power topology
approved for the exact development board and Monsoon model.
