#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${PID_FILE:-$SCRIPT_DIR/smart_plant_test.pid}"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No Smart Plant PID file exists."
    exit 0
fi

PID="$(<"$PID_FILE")"
[[ "$PID" =~ ^[0-9]+$ ]] && (( PID > 1 )) || { echo "Invalid PID file." >&2; exit 1; }
if kill -0 "$PID" 2>/dev/null; then
    if [[ ! -r "/proc/$PID/cmdline" ]] || ! tr '\0' ' ' < "/proc/$PID/cmdline" | grep -Fq "smartplant_pi.experiment_runner" || [[ "$(readlink -f "/proc/$PID/cwd")" != "$(realpath "$SCRIPT_DIR")" ]]; then
        echo "PID $PID is not this project runner; refusing to signal it." >&2; exit 1
    fi
    kill -TERM "$PID"
    # Allow camera timeout, ONNX request timeout and orderly worker shutdown.
    for _ in {1..600}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 0.2
    done
fi
if kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID did not stop cleanly; PID file was preserved." >&2
    exit 1
fi
rm -f -- "$PID_FILE"
echo "Stopped Smart Plant experiment PID=$PID"
