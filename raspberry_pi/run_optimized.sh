#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Reference: one capture/inference per wake, then halt. For a bench-only run,
# explicitly set PI_SHUTDOWN_AFTER_INITIAL_CYCLE=0 and a duration.
export TEST_DURATION_SECONDS="${TEST_DURATION_SECONDS:-0}"
extra=()
[[ "${PI_SHUTDOWN_AFTER_INITIAL_CYCLE:-1}" != 1 ]] || extra+=(--shutdown-after-initial-cycle)
exec "$ROOT/run_test.sh" optimized "${extra[@]}" "$@"
