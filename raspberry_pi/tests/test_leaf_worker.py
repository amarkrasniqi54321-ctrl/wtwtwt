from pathlib import Path
import sys
import tempfile
import unittest

try:
    import onnxruntime  # noqa: F401
except ImportError:
    onnxruntime = None

from smartplant_pi.leaf_worker_client import LeafWorkerClient


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(onnxruntime is not None and (ROOT / "leaf_classifier/model.onnx").is_file(), "exact ONNX environment or model asset unavailable")
class LeafWorkerIntegrationTests(unittest.TestCase):
    def test_worker_preserves_virtual_environment_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            link = Path(temporary_directory) / "venv-python"
            try:
                link.symlink_to(Path(sys.executable))
            except (NotImplementedError, OSError):
                self.skipTest("creating a symlink is unavailable")

            self.assertNotEqual(link.absolute(), link.resolve())
            client = LeafWorkerClient(
                link, ROOT / "leaf_classifier" / "worker.py"
            )
            self.assertEqual(link.absolute(), client.python_executable.absolute())

    def test_worker_loads_once_and_classifies_multiple_images(self) -> None:
        client = LeafWorkerClient(
            Path(sys.executable), ROOT / "leaf_classifier" / "worker.py"
        )
        metadata = client.start()
        first_pid = client.pid
        try:
            self.assertEqual(1, metadata["model_load_count"])
            self.assertEqual(["CPUExecutionProvider"], metadata["providers"])
            unhealthy = client.classify(
                ROOT
                / "leaf_classifier"
                / "images"
                / "pepper_bacterial_spot.jpg"
            )
            healthy = client.classify(
                ROOT / "leaf_classifier" / "images" / "pepper_healthy.jpg"
            )
            self.assertEqual("unhealthy", unhealthy["condition"])
            self.assertEqual("healthy", healthy["condition"])
            self.assertGreaterEqual(unhealthy["inference_time_ms"], 0.0)
            self.assertGreaterEqual(healthy["prediction_time_ms"], 0.0)
            self.assertEqual(first_pid, client.pid)
        finally:
            client.stop()

    def test_missing_image_returns_real_worker_error(self) -> None:
        client = LeafWorkerClient(
            Path(sys.executable), ROOT / "leaf_classifier" / "worker.py"
        )
        client.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                client.classify(ROOT / "leaf_classifier" / "images" / "missing.jpg")
        finally:
            client.stop()


if __name__ == "__main__":
    unittest.main()
