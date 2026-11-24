"""Check ONNX asset integrity and classify known leaf test photos."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from leaf_classifier.main import load_model, classify_image


def main():
    assets = json.loads((ROOT / "ASSETS.json").read_text(encoding="utf-8"))
    for asset in assets:
        path = ROOT / asset["path"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {path.name}")
    session, labels = load_model()
    for asset in assets:
        if "expected_label" not in asset:
            continue
        condition, _, _ = classify_image(session, labels, ROOT / asset["path"])
        if condition != asset["expected_label"]:
            raise ValueError(f"Incorrect test prediction: {asset['path']}")
    print("ONNX model integrity and sample classifications: PASS")


if __name__ == "__main__":
    main()
