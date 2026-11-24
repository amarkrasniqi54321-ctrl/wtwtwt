"""Long-running JSON-lines worker for the exact FRI ONNX classifier."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

try:
    from .main import classify_image, load_model
except ImportError:  # Direct execution: python leaf_classifier/worker.py
    # Some isolated Python installations (including a Windows ``._pth``
    # runtime) do not put the script directory on sys.path.  Import through
    # the package explicitly so direct execution behaves like ``-m``.
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from leaf_classifier.main import classify_image, load_model


PROTOCOL = "fri-leaf-worker-v1"


def _emit(record: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    )
    sys.stdout.flush()


def _diagnostic(message: str) -> None:
    print(f"leaf-worker: {message}", file=sys.stderr, flush=True)


class _TimedSession:
    """Delegate to ONNX Runtime while timing only session.run()."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.inference_time_ms = 0.0

    def get_inputs(self) -> Any:
        return self.session.get_inputs()

    def run(self, output_names: Any, inputs: Any) -> Any:
        started = perf_counter()
        try:
            return self.session.run(output_names, inputs)
        finally:
            self.inference_time_ms = (perf_counter() - started) * 1000.0


def run_worker() -> int:
    try:
        session, labels = load_model()
    except Exception as error:
        _diagnostic(f"model load failed: {error}")
        _emit(
            {
                "type": "fatal",
                "protocol": PROTOCOL,
                "ok": False,
                "error": f"{type(error).__name__}: {error}",
            }
        )
        return 1

    timed_session = _TimedSession(session)
    _emit(
        {
            "type": "ready",
            "protocol": PROTOCOL,
            "ok": True,
            "providers": session.get_providers(),
            "input_shape": list(session.get_inputs()[0].shape),
            "output_shape": list(session.get_outputs()[0].shape),
            "label_count": len(labels),
            "model_load_count": 1,
        }
    )
    _diagnostic("model loaded once; waiting for image paths")

    for raw_line in sys.stdin:
        request_id: Any = None
        try:
            message = json.loads(raw_line)
            if not isinstance(message, dict):
                raise ValueError("request must be a JSON object")
            request_id = message.get("id")
            request_type = message.get("type")
            if request_type == "shutdown":
                _emit(
                    {
                        "type": "stopped",
                        "protocol": PROTOCOL,
                        "ok": True,
                    }
                )
                return 0
            if request_type != "classify":
                raise ValueError("request type must be 'classify' or 'shutdown'")
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("classification request needs a non-empty string id")
            image_path_value = message.get("image_path")
            if not isinstance(image_path_value, str) or not image_path_value:
                raise ValueError("classification request needs image_path")
            image_path = Path(image_path_value)
            if not image_path.is_file():
                raise FileNotFoundError(f"image does not exist: {image_path}")

            started = perf_counter()
            condition, healthy_score, unhealthy_score = classify_image(
                timed_session, labels, image_path
            )
            prediction_time_ms = (perf_counter() - started) * 1000.0
            _emit(
                {
                    "type": "result",
                    "protocol": PROTOCOL,
                    "id": request_id,
                    "ok": True,
                    "image_path": str(image_path),
                    "condition": condition,
                    "healthy_score": healthy_score,
                    "unhealthy_score": unhealthy_score,
                    "inference_time_ms": timed_session.inference_time_ms,
                    "prediction_time_ms": prediction_time_ms,
                }
            )
        except Exception as error:
            _diagnostic(f"request {request_id!r} failed: {error}")
            _emit(
                {
                    "type": "result",
                    "protocol": PROTOCOL,
                    "id": request_id,
                    "ok": False,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

    _diagnostic("stdin closed; stopping")
    return 0


def main() -> None:
    raise SystemExit(run_worker())


if __name__ == "__main__":
    main()
