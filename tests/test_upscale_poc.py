"""Verify safety properties of the isolated Real-ESRGAN review workflow."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

spec = importlib.util.spec_from_file_location(
    "upscale_poc", Path(__file__).resolve().parents[1] / "scripts/upscale-poc.py"
)
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


class UpscalePocTests(unittest.TestCase):
    def test_failed_inference_keeps_previous_cache_and_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cache").mkdir()
            prior = root / "cache/prior-valid-result.png"
            Image.new("RGB", (2, 2), "red").save(prior)
            original = root / "nasa-original.jpg"
            Image.new("RGB", (16, 16), "orange").save(original)
            before = original.read_bytes()
            backend = root / "failed-backend"
            backend.write_text("#!/bin/sh\nexit 5\n")
            backend.chmod(0o700)
            scene = {"source": str(original), "sha256": poc.digest(original)}
            with self.assertRaises(subprocess.CalledProcessError):
                poc.infer(root, backend, scene, 256)
            self.assertEqual(original.read_bytes(), before)
            with Image.open(prior) as retained:
                self.assertEqual(retained.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(list((root / "cache").iterdir()), [prior])

    def test_atomic_image_retains_previous_file_on_encoding_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.png"
            Image.new("RGB", (4, 4), "blue").save(output)
            before = output.read_bytes()

            class BrokenImage:
                def save(self, *_args, **_kwargs):
                    raise RuntimeError("simulated save failure")

            with self.assertRaises(RuntimeError):
                poc.atomic_image(BrokenImage(), output)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(list(Path(temporary).iterdir()), [output])


if __name__ == "__main__":
    unittest.main()
