#!/usr/bin/env python3
"""Remove only owned launch jobs and bundles; retain originals and application data."""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_store import (
    BUNDLE_PREFIX,
    LEGACY_BUNDLE_PREFIX,
    compatible_identifiers,
)

home = Path.home()
labels = [
    f"{prefix}.{component}"
    for prefix in (BUNDLE_PREFIX, LEGACY_BUNDLE_PREFIX)
    for component in ("refresh", "desktop")
]
for label in labels:
    path = home / "Library/LaunchAgents" / f"{label}.plist"
    if path.exists() and plistlib.loads(path.read_bytes()).get("Label") == label:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
            capture_output=True,
            check=False,
        )
        path.unlink()
for path, identifier in [
    (home / "Applications/Solar Horizon.app", "uk.jonh.solar-horizon.app"),
    (home / "Library/Screen Savers/Solar Horizon.saver", "uk.jonh.solar-horizon.saver"),
]:
    info = path / "Contents/Info.plist"
    if info.exists() and plistlib.loads(info.read_bytes()).get(
        "CFBundleIdentifier"
    ) in compatible_identifiers(identifier):
        shutil.rmtree(path)
print("Owned bundles and jobs removed. Originals and application data retained.")
