#!/usr/bin/env python3
"""Remove only owned launch jobs and bundles; retain originals and application data."""

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

home = Path.home()
for label in ["uk.jonh.getSDO.refresh", "uk.jonh.getSDO.desktop"]:
    path = home / "Library/LaunchAgents" / f"{label}.plist"
    if path.exists() and plistlib.loads(path.read_bytes()).get("Label") == label:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
            capture_output=True,
            check=False,
        )
        path.unlink()
for path, identifier in [
    (home / "Applications/Solar Horizon.app", "uk.jonh.getSDO.app"),
    (home / "Library/Screen Savers/Solar Horizon.saver", "uk.jonh.getSDO.saver"),
]:
    info = path / "Contents/Info.plist"
    if (
        info.exists()
        and plistlib.loads(info.read_bytes()).get("CFBundleIdentifier") == identifier
    ):
        shutil.rmtree(path)
print("Owned bundles and jobs removed. Originals and application data retained.")
