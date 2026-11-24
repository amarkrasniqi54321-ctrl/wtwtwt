"""Core BASELINE and OPTIMIZED execution tests."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from smartplant_pi.experiment_runner import ExperimentRunner


def args(root, mode="baseline", shutdown=False):
    return SimpleNamespace(
        mode=mode, events_log=root/"events.jsonl", measurements_csv=root/"data.csv",
        image_dir=root/"images", serial_device="/dev/serial0",
        onnx_python=Path("/dev/null"), leaf_worker=Path("/dev/null"),
        camera_interval_seconds=1800, duration_seconds=0.01,
        shutdown_after_initial_cycle=shutdown)


class RunnerTests(unittest.TestCase):
    def make_runner(self, root, mode="baseline", shutdown=False):
        runner = ExperimentRunner(args(Path(root), mode, shutdown))
        runner.camera = Mock()
        runner.camera.capture.return_value = SimpleNamespace(backend="mock", capture_time_ms=10)
        runner.classifier = Mock()
        runner.classifier.classify.return_value = {
            "condition": "healthy", "healthy_score": 0.8,
            "unhealthy_score": 0.2, "inference_time_ms": 3.5}
        return runner

    def test_baseline_capture_and_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp)
            self.assertTrue(runner.capture_and_classify())
            runner.camera.capture.assert_called_once()
            runner.classifier.classify.assert_called_once()

    def run_optimized(self, runner, capture_ok=True, poweroff_ok=True, cancelled=False):
        classifier = runner.classifier
        classifier.start.return_value = {"providers": ["CPUExecutionProvider"], "model_load_count": 1}
        if not capture_ok:
            classifier.classify.side_effect = RuntimeError("inference failure")
        runner.read_uart = Mock()
        if cancelled:
            runner.camera.capture.side_effect = lambda path: (runner.cancel(), SimpleNamespace(backend="mock", capture_time_ms=10))[1]
        runner.args.duration_seconds = 0
        with patch("smartplant_pi.experiment_runner.LeafWorkerClient", return_value=classifier), \
             patch("smartplant_pi.experiment_runner.os.sync"), \
             patch("smartplant_pi.experiment_runner.subprocess.run") as poweroff:
            if not poweroff_ok:
                poweroff.side_effect = RuntimeError("poweroff failed")
            result = runner.run()
        if cancelled:
            poweroff.assert_not_called()
        else:
            poweroff.assert_called_once_with(
                ["sudo", "-n", "/usr/bin/systemctl", "poweroff"], check=True, timeout=10)
        classifier.stop.assert_called_once()
        return result

    def test_optimized_shutdown_after_success(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=True)
            self.assertEqual(0, self.run_optimized(runner))
            self.assertTrue(runner.camera_cycle_success)

    def test_optimized_failure_logged_then_halt(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=True)
            self.assertEqual(0, self.run_optimized(runner, capture_ok=False))
            events = [json.loads(s) for s in (Path(temp)/"events.jsonl").read_text().splitlines()]
            self.assertIn("optimized_cycle_failed", [e["event_type"] for e in events])
            self.assertFalse(runner.camera_cycle_success)

    def test_optimized_poweroff_error_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=True)
            self.assertEqual(1, self.run_optimized(runner, poweroff_ok=False))

    def test_cancelled_optimized_run_never_halts(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=True)
            self.assertEqual(0, self.run_optimized(runner, cancelled=True))

    def test_baseline_restarts_dead_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp)
            dead = runner.classifier
            dead.is_running = False
            replacement = Mock()
            replacement.start.return_value = {"providers": ["CPUExecutionProvider"], "model_load_count": 1}
            replacement.classify.return_value = dead.classify.return_value
            with patch("smartplant_pi.experiment_runner.LeafWorkerClient", return_value=replacement):
                self.assertTrue(runner.capture_and_classify())
            dead.stop.assert_called_once()
            replacement.start.assert_called_once()
            replacement.classify.assert_called_once()

    def test_manual_optimized_cycle_never_halts(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=False)
            with patch("smartplant_pi.experiment_runner.subprocess.run") as poweroff:
                runner.camera_loop()
            poweroff.assert_not_called()
            self.assertTrue(runner.camera_cycle_complete.is_set())

    def test_optimized_model_start_failure_halts_for_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=True)
            runner.classifier.start.side_effect = RuntimeError("model unavailable")
            with patch("smartplant_pi.experiment_runner.LeafWorkerClient", return_value=runner.classifier), \
                 patch("smartplant_pi.experiment_runner.os.sync"), \
                 patch("smartplant_pi.experiment_runner.subprocess.run") as poweroff:
                self.assertEqual(0, runner.run())
            poweroff.assert_called_once()
            runner.classifier.stop.assert_called_once()

    def test_camera_failure_halts_for_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = self.make_runner(temp, mode="optimized", shutdown=True)
            runner.camera.capture.side_effect = RuntimeError("camera unplugged")
            self.assertEqual(0, self.run_optimized(runner))
            self.assertFalse(runner.camera_cycle_success)


if __name__ == "__main__":
    unittest.main()
