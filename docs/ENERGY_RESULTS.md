# Energy results and methodology

The Monsoon Power Monitor measured the combined Main power channel during short experimental runs. Component breakdowns below are inferred from waveform events, not measurements of electrically isolated parts.

## Historical BASELINE (not current firmware)

ESP32 reads air temperature, air humidity and soil moisture approximately every 2 s. Raspberry Pi logs UART messages and runs CSI capture + ONNX classification approximately every 60 s.

Modelled six-day energy: **273.68 Wh** (average **1.9006 W**). Approximate breakdown: base/background **262.86 Wh**, sensing/logging **3.79 Wh**, camera/ONNX **7.03 Wh**.

## OPTIMIZED (measured test)

The historical short bench-test profile used 10 s ESP32 timer Deep Sleep and wakes Pi every 10 sensing cycles. Analysis of two Monsoon recordings yielded:

| Measured/inferred quantity | Value |
| --- | ---: |
| Low-activity power (Main channel) | 1.339330 W |
| Incremental sensing event energy | 0.092838 J |
| Incremental combined Pi activity block energy | 55.848094 J |
| Pi activity block duration | ~34.72 s |

The activity-block estimate includes overlapping sensing events; projection avoids counting them twice.

## Six-day calculation (not directly measured)

Assume 20 s ESP32 Deep Sleep + ~0.334625 s awake overhead and one Pi wake every 360 cycles; 25,493 sensing events and 70 Pi activations over 518,400 s.

**BASELINE: 273.68 Wh. OPTIMIZED: 194.60 Wh. Estimated saving: 79.08 Wh / 28.89%.**

Optimized breakdown: background **192.86 Wh (99.1%)**, sensing **0.66 Wh**, Pi/camera/ONNX incremental **1.08 Wh**.

The previous firmware revision implemented the model's 20 s / 360-cycle configuration. The current adaptive scenario is separate; see [ADAPTIVE_SCENARIO.md](ADAPTIVE_SCENARIO.md). Historical recordings used 10 s / 10 cycles; no six-day hardware measurement was performed. The updated code has not been validated by those historical traces. Low-activity Pi HALT state, measurement boundary and exceptional alarms were not independently quantified. This simplified source edition also differs from the exact firmware/software revisions used during historic Monsoon recordings; do not present those traces as direct validation of this edition.
