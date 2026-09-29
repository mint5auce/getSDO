#!/usr/bin/env python3
"""Build and install the personal macOS app, saver and daily refresh job."""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
SUPPORT = HOME / "Library/Application Support/getSDO"


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def owned_copy(source, destination, identifier):
    if destination.exists():
        info = destination / "Contents/Info.plist"
        if (
            not info.exists()
            or plistlib.loads(info.read_bytes()).get("CFBundleIdentifier") != identifier
        ):
            raise RuntimeError(f"Refusing to overwrite unrelated bundle: {destination}")
    # Loaded executables must keep their original inode until their host exits.
    # Replacing files inside a loaded bundle can leave a cached, mixed version.
    staging = Path(
        tempfile.mkdtemp(prefix=".solar-horizon-install-", dir=destination.parent)
    )
    replacement = staging / destination.name
    backup = SUPPORT / "installation-backups" / uuid.uuid4().hex / destination.name
    try:
        shutil.copytree(source, replacement)
        if destination.exists():
            backup.parent.mkdir(parents=True)
            destination.rename(backup)
        try:
            replacement.rename(destination)
        except OSError:
            if backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
    finally:
        shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--originals", type=Path, default=None)
    args = parser.parse_args()
    config_path = SUPPORT / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    originals = (
        Path(args.originals or config.get("originals", HOME / "Pictures/sdo-feed"))
        .expanduser()
        .resolve()
    )
    support = SUPPORT.resolve()
    if (
        originals == support
        or originals in support.parents
        or support in originals.parents
    ):
        parser.error("Originals and application data must be separate")
    run(ROOT / "scripts/build-macos.sh")
    for label in ("uk.jonh.getSDO.desktop", "uk.jonh.getSDO.refresh"):
        path = HOME / "Library/LaunchAgents" / f"{label}.plist"
        if path.exists():
            if plistlib.loads(path.read_bytes()).get("Label") != label:
                raise RuntimeError(f"Refusing to stop unrelated job: {path}")
            subprocess.run(
                ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
                capture_output=True,
                check=False,
            )
    runtime = SUPPORT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    for name in [
        "getSDO.py",
        "wallpaper.py",
        "solar_scene.py",
        "scene_store.py",
        "refresh.py",
        "requirements-wallpaper.txt",
    ]:
        shutil.copy2(ROOT / name, runtime / name)
    if not (runtime / ".venv/bin/python").exists():
        run(sys.executable, "-m", "venv", runtime / ".venv")
    python = runtime / ".venv/bin/python"
    run(python, "-m", "pip", "install", "-r", runtime / "requirements-wallpaper.txt")
    from scene_store import atomic_json

    config.update(
        python=str(python),
        refresh_script=str(runtime / "refresh.py"),
        originals=str(originals),
    )
    atomic_json(config_path, config)
    applications = HOME / "Applications"
    applications.mkdir(exist_ok=True)
    savers = HOME / "Library/Screen Savers"
    savers.mkdir(parents=True, exist_ok=True)
    app = applications / "Solar Horizon.app"
    owned_copy(ROOT / "build/Solar Horizon.app", app, "uk.jonh.getSDO.app")
    owned_copy(
        ROOT / "build/Solar Horizon.saver",
        savers / "Solar Horizon.saver",
        "uk.jonh.getSDO.saver",
    )
    agents = HOME / "Library/LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    jobs = [
        (
            "uk.jonh.getSDO.refresh",
            {
                "ProgramArguments": [str(python), str(runtime / "refresh.py")],
                "RunAtLoad": True,
                "StartCalendarInterval": {"Hour": 8, "Minute": 0},
                "StartInterval": 300,
            },
        ),
        (
            "uk.jonh.getSDO.desktop",
            {
                "ProgramArguments": [str(app / "Contents/MacOS/SolarHorizon")],
                "RunAtLoad": True,
            },
        ),
    ]
    for label, fields in jobs:
        path = agents / f"{label}.plist"
        job = {"Label": label, **fields, "ProcessType": "Background"}
        if path.exists() and plistlib.loads(path.read_bytes()).get("Label") != label:
            raise RuntimeError(f"Refusing to overwrite unrelated job: {path}")
        path.write_bytes(plistlib.dumps(job))
        if not args.no_start:
            subprocess.run(
                ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
                capture_output=True,
                check=False,
            )
            run("launchctl", "bootstrap", f"gui/{os.getuid()}", path)
    print(f"Installed {app} and {savers / 'Solar Horizon.saver'}")
    print(
        "Select Solar Horizon in System Settings > Screen Saver to enable the companion."
    )


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
