"""Deterministic SDO/AIA 193 Å scenes; originals are never modified."""

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from scene_store import SUPPORT, atomic_json, separate_paths

PROFILE = "teal-pewter-v3"
PERIOD = 1200.0


def validate_image(path):
    with Image.open(path) as image:
        if (
            image.format != "JPEG"
            or image.width != image.height
            or not 64 <= image.width <= 8192
        ):
            raise ValueError("Expected a square full-disc JPEG, 64-8192 pixels")
        image.verify()
    with Image.open(path) as image:
        image.load()


def limb_radius(gray):
    """Find the steepest radial limb falloff, independently of safe interior crops."""
    size = gray.shape[0]
    yy, xx = np.mgrid[:size, :size]
    radius = np.hypot(xx - (size - 1) / 2, yy - (size - 1) / 2)
    bins = radius.astype(int)
    means = np.bincount(bins.ravel(), weights=gray.ravel()) / np.maximum(
        1, np.bincount(bins.ravel())
    )
    smoothed = np.convolve(means, np.ones(5) / 5, mode="same")
    lo, hi = int(size * 0.35), int(size * 0.46)
    return float(lo + np.argmin(np.diff(smoothed)[lo:hi]))


def prepare_scene(source, support=SUPPORT, observation=None, source_url=None):
    source, support = Path(source), Path(support)
    separate_paths(source.parent, support)
    validate_image(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    identifier = f"{digest}-{PROFILE}"
    folder = support / "scenes" / identifier
    manifest_path = folder / "manifest.json"
    if manifest_path.exists() and (folder / "texture.png").exists():
        try:
            cached_manifest = json.loads(manifest_path.read_text())
            with Image.open(folder / "texture.png") as cached:
                cached.load()
                with Image.open(source) as original:
                    if cached.size != original.size:
                        raise ValueError("Cached texture dimensions differ from source")
            if (
                cached_manifest["sha256"] == digest
                and cached_manifest["profile"] == PROFILE
            ):
                return cached_manifest
        except (OSError, ValueError, KeyError):
            pass
    with Image.open(source) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
    gray = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    small = (
        np.asarray(
            Image.fromarray((gray * 255).astype("uint8")).resize((512, 512)),
            dtype=np.float32,
        )
        / 255
    )
    limb = limb_radius(small) * len(gray) / 512
    yy, xx = np.ogrid[: len(gray), : len(gray)]
    yy, xx = yy.astype(np.float32), xx.astype(np.float32)
    radius = np.hypot(xx - (len(gray) - 1) / 2, yy - (len(gray) - 1) / 2) / limb
    # Fade to black before the inscribed image edge so footer text never rotates in.
    mask = np.clip((1.13 - radius) / 0.06, 0, 1)
    mask *= np.clip((0.45 * len(gray) - radius * limb) / (len(gray) * 0.02), 0, 1)
    low, high = map(float, np.percentile(gray[radius < 0.98], [1, 99.8]))
    luminance = np.clip((gray - low) / max(0.01, high - low), 0, 1) ** 1.15
    shadows = np.array([0.025, 0.085, 0.095], dtype=np.float32)
    midtones = np.array([0.17, 0.29, 0.30], dtype=np.float32)
    highlights = np.array([0.78, 0.77, 0.70], dtype=np.float32)
    t = luminance[..., None]
    colour = np.where(
        t < 0.55,
        shadows + (midtones - shadows) * t / 0.55,
        midtones + (highlights - midtones) * (t - 0.55) / 0.45,
    )
    # Corona remains dim, with no time-dependent brightness modulation.
    corona_gain = 1 - 0.42 * np.clip((radius - 1) / 0.08, 0, 1)
    colour *= corona_gain[..., None] * mask[..., None]
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=folder, suffix=".png", delete=False
        ) as stream:
            temporary = Path(stream.name)
            Image.fromarray((np.clip(colour, 0, 1) * 255).astype("uint8")).save(
                stream, format="PNG"
            )
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(folder / "texture.png")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    manifest = {
        "schema": 1,
        "id": identifier,
        "profile": PROFILE,
        "source": str(source.resolve()),
        "sha256": digest,
        "observation": observation,
        "source_url": source_url,
        "channel": "SDO/AIA 193 Å",
        "texture": str((folder / "texture.png").resolve()),
        "limb_uv": limb / len(gray),
        "period": PERIOD,
        "apex": 0.48,
        "radius_widths": 1.0,
        "glow": "static restrained corona",
    }
    atomic_json(manifest_path, manifest)
    return manifest


def phase(seconds):
    return (seconds % PERIOD) / PERIOD * math.tau


def preview(manifest, target, size=(1672, 941), seconds=0):
    """Same inverse mapping as the Metal renderer, useful for deterministic QA."""
    width, height = size
    yy, xx = np.mgrid[:height, :width]
    dx = (xx + 0.5) / width - 0.5
    disc_radius = max(1, 1.16 * height / width)
    dy = (yy + 0.5) / width - (manifest["apex"] * height / width + disc_radius)
    angle = phase(seconds)
    u = (
        0.5
        + (dx * math.cos(angle) + dy * math.sin(angle))
        * manifest["limb_uv"]
        / disc_radius
    )
    v = (
        0.5
        + (-dx * math.sin(angle) + dy * math.cos(angle))
        * manifest["limb_uv"]
        / disc_radius
    )
    with Image.open(manifest["texture"]) as texture:
        values = np.asarray(texture)
    # Bilinear sampling, with black outside the source square.
    sx, sy = u * values.shape[1] - 0.5, v * values.shape[0] - 0.5
    x0, y0 = np.floor(sx).astype(int), np.floor(sy).astype(int)
    wx, wy = (sx - x0)[..., None], (sy - y0)[..., None]

    def sample(x, y):
        valid = (x >= 0) & (y >= 0) & (x < values.shape[1]) & (y < values.shape[0])
        return (
            values[
                np.clip(y, 0, values.shape[0] - 1), np.clip(x, 0, values.shape[1] - 1)
            ]
            * valid[..., None]
        )

    result = (sample(x0, y0) * (1 - wx) + sample(x0 + 1, y0) * wx) * (1 - wy) + (
        sample(x0, y0 + 1) * (1 - wx) + sample(x0 + 1, y0 + 1) * wx
    ) * wy
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(result, 0, 255).astype("uint8")).save(target)


def prune_scenes(support, published):
    """Prune only recognized, inactive generated scenes; never traverse symlinks."""
    pinned = {
        entry["id"]
        for entry in (published.get("current"), published.get("previous"))
        if entry
    }
    for folder in (Path(support) / "scenes").iterdir():
        if folder.is_symlink() or not folder.is_dir() or folder.name in pinned:
            continue
        if not re.fullmatch(r"[a-f0-9]{64}-teal-pewter-v[0-9]+", folder.name):
            continue
        try:
            manifest = json.loads((folder / "manifest.json").read_text())
            owned_files = {"texture.png", "manifest.json"}
            if any(
                entry.name not in owned_files or entry.is_symlink()
                for entry in folder.iterdir()
            ):
                continue
            if (
                isinstance(manifest, dict)
                and manifest.get("id") == folder.name
                and manifest.get("schema") == 1
            ):
                shutil.rmtree(folder)
        except (OSError, ValueError, KeyError):
            continue
