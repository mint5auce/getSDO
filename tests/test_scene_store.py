"""Check storage compatibility without moving existing observations or scenes."""

import tempfile
import unittest
from pathlib import Path

from scene_store import support_directory


class StorageCompatibilityTests(unittest.TestCase):
    def test_fresh_install_and_upgrade_choose_the_expected_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            current = home / "Library/Application Support/Solar Horizon"
            legacy = home / "Library/Application Support/getSDO"
            self.assertEqual(support_directory(home), current)
            legacy.mkdir(parents=True)
            scene = legacy / "scene.json"
            scene.write_text('{"current": "saved-scene"}')
            self.assertEqual(support_directory(home), legacy)
            self.assertFalse(current.exists())
            current.mkdir()
            self.assertEqual(support_directory(home), current)
            self.assertEqual(scene.read_text(), '{"current": "saved-scene"}')


if __name__ == "__main__":
    unittest.main()
