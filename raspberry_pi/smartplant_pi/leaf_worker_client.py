"""Client for one persistent exact-FRI ONNX classifier subprocess."""

from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import threading
from typing import Any, TextIO
import uuid


PROTOCOL = "fri-leaf-worker-v1"


class LeafWorkerError(RuntimeError):
    """Raised when the classifier worker cannot provide a real result."""


class LeafWorkerClient:
    def __init__(
        self,
        python_executable: Path,
        worker_script: Path,
        start_timeout_seconds: float = 30.0,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        if start_timeout_seconds <= 0 or request_timeout_seconds <= 0:
            raise ValueError("worker timeouts must be positive")
        self.python_executable = Path(python_executable)
        self.worker_script = Path(worker_script)
        self.start_timeout_seconds = start_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.process: subprocess.Popen[str] | None = None
        self.metadata: dict[str, Any] | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._request_lock = threading.Lock()

    @property
    def pid(self) -> int | None:
        return None if self.process is None else self.process.pid

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _read_stdout(self, stream: TextIO) -> None:
        try:
            for line in stream:
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("worker message is not an object")
                except Exception as error:
                    message = {
                        "type": "protocol_error",
                        "ok": False,
                        "error": f"invalid worker stdout: {error}",
                    }
                self._responses.put(message)
        finally:
            self._responses.put(
                {"type": "eof", "ok": False, "error": "worker stdout closed"}
            )

    def _next_message(self, timeout: float) -> dict[str, Any]:
        try:
            message = self._responses.get(timeout=timeout)
        except queue.Empty as error:
            raise LeafWorkerError("timed out waiting for classifier worker") from error
        if message.get("protocol") not in (None, PROTOCOL):
            raise LeafWorkerError("classifier worker protocol mismatch")
        if message.get("type") in {"fatal", "eof", "protocol_error"}:
            raise LeafWorkerError(str(message.get("error", "classifier worker failed")))
        return message

    def start(self) -> dict[str, Any]:
        if self.process is not None:
            raise LeafWorkerError("classifier worker is already started")
        if not self.python_executable.is_file():
            raise FileNotFoundError(
                f"ONNX Python executable is missing: {self.python_executable}"
            )
        if not self.worker_script.is_file():
            raise FileNotFoundError(
                f"classifier worker script is missing: {self.worker_script}"
            )

        # Keep the virtual-environment executable path intact. On Linux a
        # venv's bin/python is commonly a symlink to the base interpreter;
        # resolving that symlink bypasses the venv and loses its site-packages.
        python_executable = self.python_executable.expanduser().absolute()
        worker_script = self.worker_script.expanduser().resolve()
        self.process = subprocess.Popen(
            [str(python_executable), "-u", str(worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        assert self.process.stdout is not None
        self._reader = threading.Thread(
            target=self._read_stdout,
            args=(self.process.stdout,),
            name="leaf-worker-protocol-reader",
            daemon=True,
        )
        self._reader.start()
        try:
            ready = self._next_message(self.start_timeout_seconds)
            if ready.get("type") != "ready" or ready.get("ok") is not True:
                raise LeafWorkerError("classifier worker did not send ready status")
            self.metadata = ready
            return ready
        except Exception:
            self._terminate()
            raise

    def classify(self, image_path: Path) -> dict[str, Any]:
        with self._request_lock:
            process = self.process
            if process is None or process.poll() is not None:
                raise LeafWorkerError("classifier worker is not running")
            request_id = uuid.uuid4().hex
            request = {
                "type": "classify",
                "protocol": PROTOCOL,
                "id": request_id,
                "image_path": str(Path(image_path).resolve()),
            }
            assert process.stdin is not None
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
            try:
                response = self._next_message(self.request_timeout_seconds)
            except Exception:
                self._terminate()
                raise
            if response.get("type") != "result" or response.get("id") != request_id:
                self._terminate()
                raise LeafWorkerError("classifier worker returned an unexpected response")
            if response.get("ok") is not True:
                raise LeafWorkerError(str(response.get("error", "classification failed")))
            return response

    def _terminate(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._close_process_streams(process)

    @staticmethod
    def _close_process_streams(process: subprocess.Popen[str]) -> None:
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()

    def stop(self) -> None:
        with self._request_lock:
            process = self.process
            if process is None:
                return
            if process.poll() is None and process.stdin is not None:
                try:
                    process.stdin.write(
                        json.dumps({"type": "shutdown", "protocol": PROTOCOL}) + "\n"
                    )
                    process.stdin.flush()
                    process.wait(timeout=5)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    self._terminate()
            self._close_process_streams(process)
            self.process = None

    def __enter__(self) -> "LeafWorkerClient":
        self.start()
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.stop()
