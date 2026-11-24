#!/usr/bin/env bash
# Install two isolated runtime environments without modifying system Picamera2.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT"
command -v python3.11 >/dev/null || {
    echo 'Requires Raspberry Pi OS Bookworm 64-bit with Python 3.11.' >&2
    exit 1
}
python3.11 - <<'PYTHON'
from picamera2 import Picamera2
import numpy, PIL
print('System Picamera2 / NumPy / Pillow available')
PYTHON
python3.11 -m venv --system-site-packages .venv-camera
.venv-camera/bin/python -m pip install -r requirements-camera.txt
python3.11 -m venv .venv-onnx
.venv-onnx/bin/python -m pip install -r leaf_classifier/requirements.txt
python3.11 - <<'PYTHON'
from pathlib import Path
import hashlib, json, urllib.request
root=Path('leaf_classifier')
asset=next(a for a in json.loads((root/'ASSETS.json').read_text()) if a['path']=='model.onnx')
p=root/'model.onnx'
if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=asset['sha256']:
    tmp=p.with_name(p.name+'.download')
    try:
        print('Downloading licensed ONNX model (~17 MB)...')
        with urllib.request.urlopen(asset['url'], timeout=90) as response, tmp.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if hashlib.sha256(tmp.read_bytes()).hexdigest()!=asset['sha256']:
            raise RuntimeError('ONNX model SHA-256 verification failed')
        tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)
print('ONNX model SHA-256 verified')
PYTHON
.venv-onnx/bin/python leaf_classifier/verify_install.py
echo 'Ready: both Python environments and the verified ONNX model.'
echo 'Run ./check_raspberry_pi.sh with the physical camera attached.'
