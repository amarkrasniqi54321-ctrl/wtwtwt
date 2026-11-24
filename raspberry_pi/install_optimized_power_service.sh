#!/usr/bin/env bash
# Install the autonomous Pi wake / image / ONNX / shutdown service.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
RUN_USER="${SUDO_USER:-$(id -un)}"
SERVICE_NAME="smartplant-optimized.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
SUDOERS_FILE="/etc/sudoers.d/smartplant-poweroff"
case "$ROOT" in
    *' '*|*$'\t'*|*'&'*|*'|')
        echo 'Project directory must not contain spaces, tabs, & or |.' >&2
        exit 1 ;;
esac
[[ "$RUN_USER" != root ]] || { echo "Run as the normal Pi user (with sudo privileges)." >&2; exit 1; }
[[ "$RUN_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || {
    echo "Unexpected Linux username: $RUN_USER" >&2; exit 1;
}
[[ -x "$ROOT/.venv-camera/bin/python" && -x "$ROOT/.venv-onnx/bin/python" ]] || {
    echo 'Run ./prepare_raspberry_pi.sh before installing the service.' >&2
    exit 1
}
[[ -f "$ROOT/leaf_classifier/model.onnx" ]] || {
    echo 'ONNX model missing.' >&2; exit 1;
}
[[ ! -f /boot/firmware/config.txt ]] ||
  ! grep -Eq '^[[:space:]]*dtoverlay=gpio-shutdown' /boot/firmware/config.txt || {
    echo 'Remove dtoverlay=gpio-shutdown: conflicts with GPIO3 wake.' >&2
    exit 1
  }
if ! command -v rpi-eeprom-config >/dev/null 2>&1; then
    echo "Missing rpi-eeprom-config: install/check Raspberry Pi 4 bootloader tools." >&2; exit 1
fi
if command -v rpi-eeprom-config >/dev/null 2>&1; then
    CFG="$(sudo rpi-eeprom-config)"
    for expected in WAKE_ON_GPIO=1 POWER_OFF_ON_HALT=0; do
        grep -Eq "^[[:space:]]*$expected[[:space:]]*$" <<<"$CFG" || {
            echo "Pi EEPROM must contain $expected." >&2; exit 1;
        }
    done
fi
TMP="$(mktemp)"
trap 'rm -f -- "$TMP"' EXIT
sed -e "s|@PROJECT_DIR@|$ROOT|g" -e "s|@RUN_USER@|$RUN_USER|g" \
    "$ROOT/systemd/$SERVICE_NAME" >"$TMP"
sudo install -m 0644 "$TMP" "$SERVICE_FILE"
printf '%s\n' "$RUN_USER ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff" >"$TMP"
sudo visudo -cf "$TMP" >/dev/null
sudo install -m 0440 "$TMP" "$SUDOERS_FILE"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo 'Service installed for the NEXT Raspberry Pi boot; not started now.'
if [[ -e /boot/firmware/smartplant-maintenance ]]; then
    echo 'Maintenance marker present; autonomous start is disabled until removed.' >&2
fi
