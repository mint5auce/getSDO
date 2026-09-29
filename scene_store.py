"""Shared storage contracts, with no image-processing dependencies."""

import json
import os
import tempfile
from pathlib import Path

SUPPORT = Path.home() / "Library/Application Support/getSDO"


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
