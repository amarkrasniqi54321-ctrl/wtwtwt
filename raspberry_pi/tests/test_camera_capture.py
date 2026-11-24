from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import smartplant_pi.camera_capture as camera_capture_module
from smartplant_pi.camera_capture import (
    CameraCapture,
    CameraStatus,
    CameraUnavailableError,
    build_camera_command,
    timestamped_image_path,
)


class CameraCaptureTests(unittest.TestCase):
    def test_missing_camera_is_reported_without_creating_an_image(self) -> None:
        camera = CameraCapture(backend="auto", warmup_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist.jpg"
            with (
                patch.object(
                    camera_capture_module.importlib,
                    "import_module",
                    side_effect=ImportError("missing"),
                ),
                patch.object(camera_capture_module.shutil, "which", return_value=None),
            ):
                status = camera.detect()
                self.assertFalse(status.available)
                with self.assertRaises(CameraUnavailableError):
                    camera.capture(output)
            self.assertFalse(output.exists())

    def test_picamera2_detection_reports_real_camera_metadata(self) -> None:
        class FakePicamera2:
            @staticmethod
            def global_camera_info():
                return [{"Model": "imx708"}]

        camera = CameraCapture(backend="picamera2", warmup_seconds=0)
        with patch(
            "smartplant_pi.camera_capture.importlib.import_module",
            return_value=SimpleNamespace(Picamera2=FakePicamera2),
        ):
            status = camera.detect()
        self.assertTrue(status.available)
        self.assertEqual("picamera2", status.backend)
        self.assertIn("imx708", status.detail)

    def test_fallback_command_is_expanded_without_a_shell(self) -> None:
        command = build_camera_command(
            "rpicam-still --camera {camera} --width {width} --height {height} --output {output}",
            Path("images/a file.jpg"),
            camera_index=1,
            width=640,
            height=480,
        )
        self.assertEqual("rpicam-still", command[0])
        self.assertIn("1", command)
        self.assertIn("640", command)
        self.assertEqual(str(Path("images/a file.jpg")), command[-1])

    def test_timestamped_name_uses_jpeg_extension(self) -> None:
        path = timestamped_image_path(Path("images"))
        self.assertEqual("images", path.parent.name)
        self.assertTrue(path.name.startswith("plant_"))
        self.assertEqual(".jpg", path.suffix)

    def test_partial_image_is_removed_after_capture_error(self) -> None:
        camera = CameraCapture(backend="picamera2", warmup_seconds=0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "partial.jpg"

            def fail_after_write(path: Path) -> None:
                path.write_bytes(b"partial")
                raise RuntimeError("camera disconnected")

            with (
                patch.object(
                    camera,
                    "detect",
                    return_value=CameraStatus(True, "picamera2", 1, "imx708"),
                ),
                patch.object(camera, "_capture_picamera2", side_effect=fail_after_write),
            ):
                with self.assertRaisesRegex(RuntimeError, "disconnected"):
                    camera.capture(output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
