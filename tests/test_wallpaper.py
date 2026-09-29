"""Exercise crop composition, pixel geometry and safe wallpaper publication."""

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import numpy as np
    from PIL import Image, ImageDraw

    import wallpaper
except ImportError:
    wallpaper = None


def solar_fixture(size=512):
    """An off-centre dark channel, textured disc and distracting white footer."""
    yy, xx = np.indices((size, size), dtype=float)
    x, y = xx / size, yy / size
    disc = (x - 0.5) ** 2 + (y - 0.5) ** 2 < 0.41**2
    along = ((x - 0.60) - (y - 0.59)) / math.sqrt(2)
    across = ((x - 0.60) + (y - 0.59)) / math.sqrt(2)
    hole = (along / 0.30) ** 2 + (across / 0.047) ** 2 < 1
    light = 170 + 24 * np.sin(x * 140) * np.cos(y * 120)
    light[hole] = 8
    light[~disc] = 0
    rgb = np.stack([light, light * 0.65, light * 0.25], axis=-1).astype("uint8")
    image = Image.fromarray(rgb)
    ImageDraw.Draw(image).rectangle((0, size * 0.96, size, size), fill="white")
    return image


@unittest.skipIf(wallpaper is None, "install requirements-wallpaper.txt for crop tests")
class CropTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.source = self.work / "solar source.png"
        self.output = self.work / "wallpapers"
        self.image = solar_fixture()
        self.image.save(self.source)

    def test_selects_dark_channel_and_excludes_space_and_footer(self):
        crop = wallpaper.select_crop(self.image, (640, 360))
        for x, y in crop.corners():
            self.assertLess(math.hypot(x - 256, y - 256), 512 * 0.41)
        result = np.asarray(wallpaper.render_crop(self.image, crop, (640, 360)))
        # Enough of the known dark feature survives; an arbitrary centre crop
        # or a brightest-pixel selector cannot satisfy both composition checks.
        dark = result[:, :, 0] < 35
        self.assertGreater(dark.mean(), 0.12)
        self.assertLess(dark.mean(), 0.5)
        self.assertFalse(np.any(np.all(result > 230, axis=-1)))
        self.assertGreater(crop.center_x, self.image.width * 0.53)

    def test_selection_follows_a_moving_feature_and_is_repeatable(self):
        first = wallpaper.select_crop(self.image, (640, 360))
        self.assertEqual(first, wallpaper.select_crop(self.image, (640, 360)))
        mirrored = self.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        second = wallpaper.select_crop(mirrored, (640, 360))
        self.assertGreater(first.center_x - second.center_x, self.image.width * 0.06)

    def test_portrait_and_ultrawide_stay_inside_the_disc(self):
        for size in ((360, 640), (1024, 256), (256, 1024), (400, 400)):
            with self.subTest(size=size):
                crop = wallpaper.select_crop(self.image, size)
                self.assertAlmostEqual(crop.width / crop.height, size[0] / size[1])
                for x, y in crop.corners():
                    self.assertLess(math.hypot(x - 256, y - 256), 512 * 0.41)
                self.assertEqual(
                    wallpaper.render_crop(self.image, crop, size).size, size
                )

    def test_rendered_pixels_match_reported_source_coordinates(self):
        yy, xx = np.indices((256, 256), dtype="uint8")
        grid = Image.fromarray(np.stack([xx, yy, np.zeros_like(xx)], axis=-1))
        crop = wallpaper.Crop(150, 140, 80, 40, 30, 0)
        result = wallpaper.render_crop(grid, crop, (160, 80))
        cosine, sine = math.cos(math.radians(30)), math.sin(math.radians(30))
        for x, y in ((20, 20), (80, 40), (140, 60)):
            dx, dy = (x + 0.5) / 2 - 40, (y + 0.5) / 2 - 20
            expected = (150 + cosine * dx - sine * dy, 140 + sine * dx + cosine * dy)
            actual = result.getpixel((x, y))
            self.assertAlmostEqual(actual[0], expected[0], delta=2)
            self.assertAlmostEqual(actual[1], expected[1], delta=2)

    def test_creation_records_provenance_preserves_original_and_skips_repeat(self):
        source_bytes = self.source.read_bytes()
        status, path, metadata = wallpaper.create_wallpaper(
            self.source, self.output, (640, 360)
        )
        self.assertEqual(status, "Created wallpaper")
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertEqual(
            metadata["source_sha256"], hashlib.sha256(source_bytes).hexdigest()
        )
        with Image.open(path) as image:
            image.load()
            self.assertEqual(image.size, (640, 360))
            self.assertEqual(json.loads(image.getexif()[270]), metadata)
        before = path.stat().st_mtime_ns
        with patch.object(
            wallpaper, "select_crop", side_effect=AssertionError("cache missed")
        ):
            status, again, cached = wallpaper.create_wallpaper(
                self.source, self.output, (640, 360)
            )
        self.assertEqual(status, "Skipped wallpaper")
        self.assertEqual(again, path)
        self.assertEqual(cached, metadata)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_changed_source_and_output_size_invalidate_cache(self):
        _, path, before = wallpaper.create_wallpaper(
            self.source, self.output, (640, 360)
        )
        self.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(self.source)
        status, again, after = wallpaper.create_wallpaper(
            self.source, self.output, (640, 360)
        )
        self.assertEqual(status, "Created wallpaper")
        self.assertEqual(path, again)
        self.assertNotEqual(before["source_sha256"], after["source_sha256"])
        _, portrait, _ = wallpaper.create_wallpaper(
            self.source, self.output, (360, 640)
        )
        self.assertNotEqual(portrait, path)
        self.assertTrue(path.is_file())

    def test_corrupt_or_incomplete_cache_is_repaired(self):
        _, target, metadata = wallpaper.create_wallpaper(
            self.source, self.output, (640, 360)
        )
        target.write_bytes(b"\xff\xd8\xfftruncated\xff\xd9")
        self.assertEqual(
            wallpaper.create_wallpaper(self.source, self.output, (640, 360))[0],
            "Created wallpaper",
        )
        metadata.pop("crop")
        exif = Image.Exif()
        exif[270] = json.dumps(metadata)
        Image.new("RGB", (640, 360)).save(target, exif=exif)
        self.assertEqual(
            wallpaper.create_wallpaper(self.source, self.output, (640, 360))[0],
            "Created wallpaper",
        )

    def test_failed_forced_write_preserves_previous_wallpaper(self):
        _, target, _ = wallpaper.create_wallpaper(self.source, self.output, (640, 360))
        before = target.read_bytes()
        with (
            patch.object(Path, "replace", side_effect=OSError("disk write failed")),
            self.assertRaisesRegex(OSError, "disk write failed"),
        ):
            wallpaper.create_wallpaper(self.source, self.output, (640, 360), force=True)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(self.output.glob(".getSDO-*")))

    def test_invalid_sources_fail_without_publishing(self):
        for image in (
            Image.new("RGB", (512, 512)),
            Image.new("RGB", (512, 512), "white"),
            Image.new("RGB", (512, 256)),
            Image.new("RGB", (64, 64)),
        ):
            with self.subTest(size=image.size, pixel=image.getpixel((0, 0))):
                image.save(self.source)
                with self.assertRaises(ValueError):
                    wallpaper.create_wallpaper(self.source, self.output, (640, 360))
                self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
