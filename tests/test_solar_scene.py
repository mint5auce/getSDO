import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

import getSDO
import refresh
import solar_scene


class SceneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.originals = self.root / "originals"
        self.originals.mkdir()
        self.support = self.root / "support"
        y, x = np.mgrid[:256, :256]
        radius = np.hypot(x - 127.5, y - 127.5)
        pixels = np.zeros((256, 256, 3), dtype="uint8")
        value = np.where(
            radius < 100,
            100 + 80 * np.cos(x / 11) * np.sin(y / 9),
            np.where(radius < 114, 25, 0),
        )
        pixels[:] = np.clip(value, 0, 255)[..., None]
        pixels[248:, :, :] = 255  # Simulate the NASA timestamp footer.
        self.source = self.originals / "solar.jpg"
        Image.fromarray(pixels).save(self.source, quality=98)
        self.stamp = dt.datetime(2026, 9, 29, 8, tzinfo=dt.timezone.utc)

    def test_source_unchanged_and_scene_repeatable(self):
        before = self.source.read_bytes()
        first = solar_scene.prepare_scene(self.source, self.support)
        second = solar_scene.prepare_scene(self.source, self.support)
        self.assertEqual(first, second)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(first["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(list(self.originals.iterdir()), [self.source])
        self.assertAlmostEqual(first["limb_uv"], 100 / 256, delta=0.02)

    def test_full_rotation_seam_and_black_sky_footer(self):
        scene = solar_scene.prepare_scene(self.source, self.support)
        for seconds in (0, 300, 600, 900, 1200):
            target = self.root / f"{seconds}.png"
            solar_scene.preview(scene, target, (320, 200), seconds)
            pixels = np.asarray(Image.open(target))
            self.assertLess(int(pixels[:40].max()), 4)
        self.assertEqual(
            (self.root / "0.png").read_bytes(), (self.root / "1200.png").read_bytes()
        )
        texture = np.asarray(Image.open(scene["texture"]))
        self.assertEqual(int(texture[-8:].max()), 0)

    def test_symlink_and_nested_path_rejection(self):
        with self.assertRaises(ValueError):
            solar_scene.separate_paths(self.originals, self.originals / "derived")
        link = self.root / "linked"
        link.symlink_to(self.originals)
        with self.assertRaises(ValueError):
            solar_scene.separate_paths(self.originals, link / "derived")

    def test_bad_download_never_enters_original_archive(self):
        def download(url, target, timeout):
            target.write_bytes(b"\xff\xd8\xffbroken\xff\xd9")

        with (
            patch.object(getSDO, "latest_timestamp", return_value=self.stamp),
            patch.object(getSDO, "save_image", side_effect=download),
            self.assertLogs(level="ERROR"),
            self.assertRaises(OSError),
        ):
            refresh.refresh(self.support, self.originals, True, self.stamp)
        self.assertEqual(list(self.originals.iterdir()), [self.source])
        self.assertFalse((self.support / "scene.json").exists())
        self.assertFalse(list(self.root.glob(".getSDO-stage-*")))

    def test_same_day_new_observation_publishes_without_phase_reset(self):
        def download(url, target, timeout):
            target.write_bytes(self.source.read_bytes())

        with (
            patch.object(getSDO, "latest_timestamp", return_value=self.stamp),
            patch.object(getSDO, "save_image", side_effect=download),
            patch.object(refresh, "continuous_seconds", return_value=50),
        ):
            refresh.refresh(self.support, self.originals, True, self.stamp)
            initial = json.loads((self.support / "scene.json").read_text())
            # Change source pixels to represent a distinct same-day observation.
            with Image.open(self.source) as image:
                changed_image = np.asarray(image).copy()
            changed_image[100:120, 100:120] = [140, 70, 30]
            Image.fromarray(changed_image).save(self.source)
            with (
                patch.object(
                    getSDO,
                    "latest_timestamp",
                    return_value=self.stamp + dt.timedelta(minutes=15),
                ),
                patch.object(refresh, "continuous_seconds", return_value=70),
            ):
                refresh.refresh(
                    self.support,
                    self.originals,
                    True,
                    self.stamp + dt.timedelta(minutes=15),
                )
        changed = json.loads((self.support / "scene.json").read_text())
        self.assertEqual(changed["previous"], initial["current"])
        self.assertEqual(changed["transition_start"], 70)
        self.assertEqual(changed["transition_seconds"], 10)
        self.assertEqual(len(list(self.originals.glob("aia_193_*.jpg"))), 2)

    def test_network_failure_keeps_last_good_scene(self):
        self.support.mkdir()
        sentinel = {"current": {"id": "last-good"}}
        solar_scene.atomic_json(self.support / "scene.json", sentinel)
        with (
            patch.object(getSDO, "latest_timestamp", side_effect=OSError("offline")),
            self.assertLogs(level="ERROR"),
            self.assertRaises(OSError),
        ):
            refresh.refresh(self.support, self.originals, True, self.stamp)
        self.assertEqual(
            json.loads((self.support / "scene.json").read_text()), sentinel
        )
        state = json.loads((self.support / "refresh-state.json").read_text())
        self.assertEqual(state["next_attempt"], self.stamp.timestamp() + 1800)

    def test_daily_due_and_retry_policy(self):
        morning = self.stamp.replace(hour=7)
        self.assertFalse(refresh.due({"completed_day": "2026-09-28"}, morning))
        self.assertTrue(refresh.due({"completed_day": "2026-09-28"}, self.stamp))
        self.assertFalse(
            refresh.due(
                {
                    "completed_day": "2026-09-29",
                    "next_attempt": self.stamp.timestamp() + 1800,
                },
                self.stamp,
            )
        )
        self.assertTrue(
            refresh.due(
                {
                    "completed_day": "2026-09-29",
                    "next_attempt": self.stamp.timestamp() - 1,
                },
                self.stamp,
            )
        )
        self.assertTrue(refresh.due({"completed_day": "2026-09-29"}, self.stamp, True))

    def test_corrupt_cache_is_rebuilt(self):
        scene = solar_scene.prepare_scene(self.source, self.support)
        Path(scene["texture"]).write_bytes(b"broken")
        rebuilt = solar_scene.prepare_scene(self.source, self.support)
        self.assertEqual(rebuilt["id"], scene["id"])
        with Image.open(rebuilt["texture"]) as image:
            image.load()
            self.assertEqual(image.size, (256, 256))

    def test_retries_stop_until_the_next_daily_slot(self):
        with patch.object(getSDO, "latest_timestamp", side_effect=OSError("offline")):
            when = self.stamp
            for delay in (1800, 7200, 21600, None):
                with self.assertLogs(level="ERROR"), self.assertRaises(OSError):
                    refresh.refresh(self.support, self.originals, False, when)
                state = json.loads((self.support / "refresh-state.json").read_text())
                if delay is not None:
                    self.assertEqual(state["next_attempt"], when.timestamp() + delay)
                    when += dt.timedelta(seconds=delay)
                else:
                    self.assertIsNone(state["next_attempt"])
            self.assertFalse(
                refresh.refresh(
                    self.support, self.originals, False, when + dt.timedelta(minutes=5)
                )
            )
            with self.assertLogs(level="ERROR"), self.assertRaises(OSError):
                refresh.refresh(
                    self.support,
                    self.originals,
                    False,
                    self.stamp + dt.timedelta(days=1),
                )
            self.assertEqual(
                json.loads((self.support / "refresh-state.json").read_text())["retry"],
                1,
            )

    def test_only_recognized_inactive_scenes_are_pruned(self):
        current = solar_scene.prepare_scene(self.source, self.support)
        scenes = self.support / "scenes"
        unrelated = scenes / "notes"
        unrelated.mkdir()
        (unrelated / "keep").write_text("user work")
        inactive = scenes / (("a" * 64) + "-teal-pewter-v1")
        inactive.mkdir()
        solar_scene.atomic_json(
            inactive / "manifest.json", {"schema": 1, "id": inactive.name}
        )
        symlink = scenes / (("b" * 64) + "-teal-pewter-v1")
        symlink.symlink_to(unrelated)
        solar_scene.prune_scenes(self.support, {"current": current, "previous": None})
        self.assertTrue(Path(current["texture"]).exists())
        self.assertFalse(inactive.exists())
        self.assertTrue((unrelated / "keep").exists())
        self.assertTrue(symlink.is_symlink())

    def test_portrait_never_reveals_the_centre(self):
        scene = solar_scene.prepare_scene(self.source, self.support)
        for width, height in ((200, 400), (400, 200), (600, 150)):
            disc_radius = max(1, 1.16 * height / width)
            centre = scene["apex"] * height / width + disc_radius
            self.assertGreater(centre, height / width)
            self.assertGreater((centre - height / width) / disc_radius, 0.54)

    def test_regressed_nasa_timestamp_keeps_newer_scene(self):
        self.support.mkdir()
        active = {"current": {"id": "newer", "observation": self.stamp.isoformat()}}
        solar_scene.atomic_json(self.support / "scene.json", active)
        with (
            patch.object(
                getSDO,
                "latest_timestamp",
                return_value=self.stamp - dt.timedelta(days=1),
            ),
            self.assertLogs(level="ERROR"),
            self.assertRaisesRegex(ValueError, "older observation"),
        ):
            refresh.refresh(self.support, self.originals, True, self.stamp)
        self.assertEqual(json.loads((self.support / "scene.json").read_text()), active)
        self.assertEqual(list(self.originals.iterdir()), [self.source])

    def test_phase_is_constant_speed_and_periodic(self):
        self.assertEqual(solar_scene.phase(0), solar_scene.phase(1200))
        self.assertAlmostEqual(solar_scene.phase(300), np.pi / 2)
        self.assertAlmostEqual(
            solar_scene.phase(601) - solar_scene.phase(600), np.pi / 600
        )


if __name__ == "__main__":
    unittest.main()
