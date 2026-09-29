"""Shared storage contracts, with no image-processing dependencies."""

import json
import os
import tempfile
from pathlib import Path

BUNDLE_PREFIX = "uk.jonh.solar-horizon"
LEGACY_BUNDLE_PREFIX = "uk.jonh.getSDO"


def support_directory(home=None):
    """Keep existing scenes and absolute manifest paths usable after the rename."""
    home = Path(home) if home is not None else Path.home()
    current = home / "Library/Application Support/Solar Horizon"
    legacy = home / "Library/Application Support/getSDO"
    return legacy if legacy.is_dir() and not current.exists() else current


def compatible_identifiers(identifier):
    """Recognize only the current identity and its original installation identity."""
    if identifier.startswith(BUNDLE_PREFIX + "."):
        return (identifier, LEGACY_BUNDLE_PREFIX + identifier[len(BUNDLE_PREFIX) :])
    return (identifier,)


SUPPORT = support_directory()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write((json.dumps(value, indent=2) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def separate_paths(originals, derived):
    originals, derived = originals.resolve(), derived.resolve()
    if (
        originals == derived
        or originals in derived.parents
        or derived in originals.parents
    ):
        raise ValueError(
            "Originals and application data must be separate, non-nested directories"
        )
