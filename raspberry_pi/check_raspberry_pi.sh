#!/usr/bin/env bash
# Run on the Pi with all existing runners stopped.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
MODE=""
SERIAL=0
case "${1:-}" in
    "") ;;
    --serial) SERIAL=1 ;;
    --baseline) SERIAL=1; MODE=BASELINE ;;
    --optimized) SERIAL=1; MODE=OPTIMIZED ;;
    *) echo "Usage: $0 [--serial|--baseline|--optimized]" >&2; exit 2 ;;
esac
exec 9>"$ROOT/.smartplant.lock"
flock -n 9 || { echo "Stop the active Smart Plant runner before preflight." >&2; exit 1; }
[[ -x .venv-camera/bin/python && -x .venv-onnx/bin/python ]] || { echo "Run ./prepare_raspberry_pi.sh first." >&2; exit 1; }
.venv-onnx/bin/python leaf_classifier/verify_install.py
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
# Use the same backend selection as the real runner.
timeout 90 .venv-camera/bin/python -m smartplant_pi.camera_capture --backend auto --output-dir "$TMP"
# Classify the actual captured photo, not just the bundled test images.
.venv-onnx/bin/python - "$TMP" <<'PY'
from pathlib import Path
import sys
from leaf_classifier.main import load_model, classify_image
photos = list(Path(sys.argv[1]).glob("*.jpg"))
if len(photos) != 1 or photos[0].stat().st_size == 0:
    raise SystemExit("Expected one nonempty camera photo")
session, labels = load_model()
condition, healthy, unhealthy = classify_image(session, labels, photos[0])
print(f"Actual photo inference: {condition}, healthy={healthy:.4f}, unhealthy={unhealthy:.4f}")
PY
if [[ "$SERIAL" == 1 ]]; then
    .venv-camera/bin/python - "$MODE" "${SERIAL_DEVICE:-/dev/serial0}" <<'PY'
import serial, sys, time
from smartplant_pi.serial_protocol import parse_serial_line, SerialProtocolError, UART_BAUD_RATE
expected, device = sys.argv[1:]
deadline = time.monotonic() + 50
with serial.Serial(device, UART_BAUD_RATE, timeout=0.5) as port:
    while time.monotonic() < deadline:
        try:
            payload = parse_serial_line(port.readline())
        except SerialProtocolError as e:
            print("Invalid UART record:", e)
            continue
        if payload:
            if expected and payload["mode"] != expected:
                raise SystemExit(f"Wrong ESP firmware: expected {expected}, got {payload['mode']}")
            if payload["sampling_interval_ms"] != 20000:
                raise SystemExit(f"Wrong sensor interval: {payload['sampling_interval_ms']} ms")
            print("UART:", payload["mode"], "sequence", payload["sequence"],
                  "air_valid", payload["air_valid"], "soil_valid", payload["soil_valid"])
            if not payload["air_valid"] or not payload["soil_raw_valid"]:
                raise SystemExit("Sensor read failed; check wiring and console")
            if not payload["soil_valid"]:
                raise SystemExit("Soil calibration missing; calibrate and rebuild both profiles")
            break
    else:
        raise SystemExit("No valid Smart Plant UART data received")
PY
fi
echo 'Real camera and model: PASS.'
