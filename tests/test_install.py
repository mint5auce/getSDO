"""Bundle replacement must preserve files already mapped by a macOS host."""

import importlib.util
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "solar_install", Path(__file__).resolve().parents[1] / "scripts/install.py"
)
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class BundleInstallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "build/Solar Horizon.saver"
        self.destination = self.root / "installed/Solar Horizon.saver"
        for folder, value in [(self.source, b"new"), (self.destination, b"old")]:
            (folder / "Contents/MacOS").mkdir(parents=True)
            (folder / "Contents/Info.plist").write_bytes(
                plistlib.dumps({"CFBundleIdentifier": "uk.jonh.solar-horizon.saver"})
            )
            (folder / "Contents/MacOS/Saver").write_bytes(value)
        self.support = patch.object(install, "SUPPORT", self.root / "support")
        self.support.start()
        self.addCleanup(self.support.stop)

    def test_open_executable_keeps_original_bytes_and_backup(self):
        executable = self.destination / "Contents/MacOS/Saver"
        inode = executable.stat().st_ino
        with executable.open("rb") as loaded:
            install.owned_copy(
                self.source, self.destination, "uk.jonh.solar-horizon.saver"
            )
            self.assertEqual(loaded.read(), b"old")
        self.assertEqual(executable.read_bytes(), b"new")
        self.assertNotEqual(executable.stat().st_ino, inode)
        backups = list(
            (self.root / "support").glob(
                "installation-backups/*/*/Contents/MacOS/Saver"
            )
        )
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"old")
        self.assertEqual(backups[0].stat().st_ino, inode)

    def test_unrelated_bundle_is_untouched(self):
        info = self.destination / "Contents/Info.plist"
        info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.owner"}))
        with self.assertRaisesRegex(RuntimeError, "unrelated bundle"):
            install.owned_copy(
                self.source, self.destination, "uk.jonh.solar-horizon.saver"
            )
        self.assertEqual(
            (self.destination / "Contents/MacOS/Saver").read_bytes(), b"old"
        )

    def test_failed_publication_restores_original_bundle(self):
        original_rename = Path.rename

        def fail_replacement(path, target):
            if path.parent.name.startswith(".solar-horizon-install-"):
                raise OSError("simulated publication failure")
            return original_rename(path, target)

        with (
            patch.object(Path, "rename", fail_replacement),
            self.assertRaisesRegex(OSError, "publication failure"),
        ):
            install.owned_copy(
                self.source, self.destination, "uk.jonh.solar-horizon.saver"
            )
        self.assertEqual(
            (self.destination / "Contents/MacOS/Saver").read_bytes(), b"old"
        )
        self.assertEqual(
            list(self.destination.parent.glob(".solar-horizon-install-*")), []
        )

    def test_legacy_bundle_is_upgraded_with_its_loaded_bytes_preserved(self):
        info = self.destination / "Contents/Info.plist"
        info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "uk.jonh.getSDO.saver"}))
        executable = self.destination / "Contents/MacOS/Saver"
        with executable.open("rb") as loaded:
            install.owned_copy(
                self.source, self.destination, "uk.jonh.solar-horizon.saver"
            )
            self.assertEqual(loaded.read(), b"old")
        self.assertEqual(
            plistlib.loads(info.read_bytes())["CFBundleIdentifier"],
            "uk.jonh.solar-horizon.saver",
        )

    def test_legacy_app_identifier_cannot_replace_a_saver(self):
        info = self.destination / "Contents/Info.plist"
        info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "uk.jonh.getSDO.app"}))
        with self.assertRaisesRegex(RuntimeError, "unrelated bundle"):
            install.owned_copy(
                self.source, self.destination, "uk.jonh.solar-horizon.saver"
            )
        self.assertEqual(
            (self.destination / "Contents/MacOS/Saver").read_bytes(), b"old"
        )

    def test_install_retires_legacy_jobs_and_uses_renamed_runtime(self):
        home = self.root / "home"
        agents = home / "Library/LaunchAgents"
        agents.mkdir(parents=True)
        for component in ("refresh", "desktop"):
            label = f"uk.jonh.getSDO.{component}"
            (agents / f"{label}.plist").write_bytes(plistlib.dumps({"Label": label}))
        with (
            patch.object(install, "HOME", home),
            patch.object(install, "run"),
            patch.object(install, "owned_copy"),
            patch.object(install.subprocess, "run"),
            patch.object(install.sys, "argv", ["install.py", "--no-start"]),
        ):
            install.main()
        for component in ("refresh", "desktop"):
            self.assertFalse((agents / f"uk.jonh.getSDO.{component}.plist").exists())
            label = f"uk.jonh.solar-horizon.{component}"
            job = plistlib.loads((agents / f"{label}.plist").read_bytes())
            self.assertEqual(job["Label"], label)
        runtime = self.root / "support/runtime"
        self.assertTrue((runtime / "solar_horizon.py").is_file())
        self.assertIn("import solar_horizon", (runtime / "refresh.py").read_text())

    def test_legacy_job_with_unrelated_owner_is_retained(self):
        home = self.root / "home"
        agents = home / "Library/LaunchAgents"
        agents.mkdir(parents=True)
        job = agents / "uk.jonh.getSDO.refresh.plist"
        before = plistlib.dumps({"Label": "other.owner"})
        job.write_bytes(before)
        with (
            patch.object(install, "HOME", home),
            patch.object(install.subprocess, "run") as run,
            self.assertRaisesRegex(RuntimeError, "unrelated job"),
        ):
            install.stop_job("uk.jonh.getSDO.refresh", remove=True)
        run.assert_not_called()
        self.assertEqual(job.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
