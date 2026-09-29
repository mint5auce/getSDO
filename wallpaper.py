"""Select a solar-surface composition locally, using only real image pixels."""

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ALGORITHM = "plasma-v1"
METADATA_TAG = 270  # EXIF ImageDescription: provenance travels with the wallpaper.


@dataclass(frozen=True)
class Crop:
    center_x: float
    center_y: float
    width: float
    height: float
    angle: int
    score: float

    def corners(self) -> list[tuple[float, float]]:
        """Map the four corners back to the unrotated source image."""
        cosine = math.cos(math.radians(self.angle))
        sine = math.sin(math.radians(self.angle))
        return [
            (
                self.center_x + cosine * x - sine * y,
                self.center_y + sine * x + cosine * y,
            )
            for x, y in (
                (-self.width / 2, -self.height / 2),
                (self.width / 2, -self.height / 2),
                (self.width / 2, self.height / 2),
                (-self.width / 2, self.height / 2),
            )
        ]


def solar_radius(gray: np.ndarray) -> float:
    """Locate the limb of a centred SDO disc using its radial brightness drop.

    Annular medians suppress active regions and dark holes; an inset excludes
    the limb, corona and footer even after rotating a candidate rectangle.
    This intentionally accepts full-disc SDO images, not arbitrary photographs.
    """
    height, width = gray.shape
    yy, xx = np.indices(gray.shape)
    radii = np.hypot(xx + 0.5 - width / 2, yy + 0.5 - height / 2).astype(int)
    limit = min(width, height) // 2
    profile = np.array([np.median(gray[radii == r]) for r in range(limit)])
    smoothed = np.convolve(profile, np.array([1, 2, 3, 2, 1]) / 9, mode="valid")
    # Avoid the convolution boundaries and search only the expected SDO limb.
    start, stop = int(limit * 0.64), int(limit * 0.96)
    drops = smoothed[start - 2 : stop - 2] - smoothed[start + 2 : stop + 2]
    limb = start + int(np.argmax(drops)) + 2
    interior = profile[int(limb * 0.25) : int(limb * 0.8)]
    if np.median(interior) < 3 or drops.max() < max(2, np.max(profile) * 0.025):
        raise ValueError(
            "Could not locate a solar disc; use a centred full-disc SDO image"
        )
    return limb - max(4, limit * 0.05)


def select_crop(image: Image.Image, size: tuple[int, int]) -> Crop:
    """Rank inset regions by dark structure, contrast, detail and diagonal flow.

    Analysis uses a small preview, with no model, network access or random seed.
    Identical pixels and output aspect ratio always produce the same crop.
    """
    width, height = image.size
    if min(width, height) < 128 or abs(width / height - 1) > 0.05:
        raise ValueError("Use a square full-disc SDO image at least 128 pixels wide")
    preview = image.convert("L")
    preview.thumbnail((320, 320), Image.Resampling.LANCZOS)
    pw, ph = preview.size
    gray = np.asarray(preview, dtype=float)
    radius = solar_radius(gray)
    yy, xx = np.indices(gray.shape)
    disc = (xx + 0.5 - pw / 2) ** 2 + (yy + 0.5 - ph / 2) ** 2 <= radius**2
    low, high = np.percentile(gray[disc], [5, 95])
    if high - low < 3:
        raise ValueError("Solar surface has too little contrast to select a crop")

    aspect = size[0] / size[1]
    candidates = []
    step = max(3, round(radius / 12))
    for angle in (0, -15, 15, -30, 30, -45, 45, -60, 60):
        rotated = preview.rotate(angle, resample=Image.Resampling.BICUBIC)
        normalized = np.clip(
            (np.asarray(rotated, dtype=float) - low) / (high - low), 0, 1
        )
        # Suppress JPEG noise before measuring local plasma structure.
        smooth = np.asarray(rotated.filter(ImageFilter.GaussianBlur(0.7)), dtype=float)
        gy, gx = np.gradient(smooth / (high - low))
        detail = np.hypot(gx, gy)
        for fraction in (0.58, 0.72, 0.86):
            diagonal = 2 * radius * fraction
            cw = max(4, round(diagonal * aspect / math.hypot(aspect, 1)))
            ch = max(4, math.ceil(cw / aspect))
            for top in range(round(ph / 2 - radius), round(ph / 2 + radius - ch), step):
                for left in range(
                    round(pw / 2 - radius), round(pw / 2 + radius - cw), step
                ):
                    right, bottom = left + cw, top + ch
                    # A rectangle inside a convex circle has all its pixels inside.
                    if any(
                        (x - pw / 2) ** 2 + (y - ph / 2) ** 2 > radius**2
                        for x in (left, right)
                        for y in (top, bottom)
                    ):
                        continue
                    patch = normalized[top:bottom, left:right]
                    dark = float(np.mean(patch < 0.23))
                    bright = float(np.mean(patch > 0.65))
                    # Reward some quiet darkness alongside bright structure, not
                    # a uniformly black patch or an isolated saturated active spot.
                    balance = min(dark / 0.22, 1) * max(0, min((0.6 - dark) / 0.25, 1))
                    score = (
                        1.8 * balance
                        + 1.5 * float(patch.std())
                        + 0.4 * min(bright / 0.12, 1)
                        + 0.3
                        * min(float(detail[top:bottom, left:right].mean()) / 0.07, 1)
                        + 0.15 * fraction
                    )
                    candidates.append((score, angle, left, top, cw, ch))

    if not candidates:
        raise ValueError("No safe solar-surface crop fits this aspect ratio")

    # Refine a shortlist with the direction of its dark structure. Covariance
    # favours a connected-looking elongated diagonal over a round dark spot.
    best = None
    for score, angle, left, top, cw, ch in sorted(candidates, reverse=True)[:48]:
        rotated = preview.rotate(angle, resample=Image.Resampling.BICUBIC)
        patch = (
            np.asarray(rotated, dtype=float)[top : top + ch, left : left + cw] - low
        ) / (high - low)
        weights = np.clip(0.23 - patch, 0, 0.23)
        mass = weights.sum()
        if mass > 0:
            py, px = np.indices(patch.shape)
            dx = px - np.sum(px * weights) / mass
            dy = py - np.sum(py * weights) / mass
            vx = float(np.sum(weights * dx * dx) / mass)
            vy = float(np.sum(weights * dy * dy) / mass)
            covariance = float(np.sum(weights * dx * dy) / mass)
            diagonal_flow = 2 * abs(covariance) / max(vx + vy, 1)
            score += 0.45 * diagonal_flow
        # A small tie preference preserves north-up when rotation adds no value.
        score -= abs(angle) * 0.0001
        if best is None or score > best[0]:
            best = (score, angle, left, top, cw, ch)

    score, angle, left, top, cw, ch = best
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    dx, dy = left + cw / 2 - pw / 2, top + ch / 2 - ph / 2
    scale = width / pw
    # Centre is in original source coordinates; width/height are along crop axes.
    return Crop(
        (pw / 2 + cosine * dx - sine * dy) * scale,
        (ph / 2 + sine * dx + cosine * dy) * scale,
        cw * scale,
        cw / aspect * scale,
        angle,
        score,
    )


def render_crop(image: Image.Image, crop: Crop, size: tuple[int, int]) -> Image.Image:
    """Rotate/crop once at source scale, then resize without stretching."""
    native = (round(crop.width), round(crop.height))
    cosine, sine = (
        math.cos(math.radians(crop.angle)),
        math.sin(math.radians(crop.angle)),
    )
    sx, sy = crop.width / native[0], crop.height / native[1]
    matrix = (
        cosine * sx,
        -sine * sy,
        crop.center_x - cosine * crop.width / 2 + sine * crop.height / 2,
        sine * sx,
        cosine * sy,
        crop.center_y - sine * crop.width / 2 - cosine * crop.height / 2,
    )
    result = image.convert("RGB").transform(
        native, Image.Transform.AFFINE, matrix, Image.Resampling.BICUBIC
    )
    return result.resize(size, Image.Resampling.LANCZOS)


def create_wallpaper(
    source: Path, output: Path, size: tuple[int, int], force: bool = False
) -> tuple[str, Path, dict]:
    """Save separately and atomically; reuse only a fully decoded matching crop."""
    source_bytes = source.read_bytes()
    fingerprint = hashlib.sha256(source_bytes).hexdigest()
    provenance = {
        "algorithm": ALGORITHM,
        "source_sha256": fingerprint,
        "size": list(size),
    }
    destination = output / f"{source.stem}_{ALGORITHM}_{size[0]}x{size[1]}.jpg"
    if destination.resolve() == source.resolve():
        raise ValueError("Wallpaper destination must be different from the source")
    if not force and destination.is_file():
        try:
            with Image.open(destination) as existing:
                metadata = json.loads(existing.getexif().get(METADATA_TAG, "{}"))
                existing.load()
                cached_crop = metadata.get("crop", {})
                if (
                    existing.size == size
                    and all(metadata.get(k) == v for k, v in provenance.items())
                    and isinstance(cached_crop, dict)
                    and all(
                        isinstance(cached_crop.get(key), (int, float))
                        and math.isfinite(cached_crop[key])
                        for key in ("width", "height", "angle")
                    )
                ):
                    return "Skipped wallpaper", destination, metadata
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
            Image.DecompressionBombError,
        ):
            pass  # Repair a corrupt, unrelated or incomplete cached result.

    try:
        original = Image.open(BytesIO(source_bytes))
    except Image.DecompressionBombError as error:
        raise ValueError("Source image is too large to crop safely") from error
    with original:
        if original.width * original.height > 40_000_000:
            raise ValueError("Source image exceeds the 40 megapixel limit")
        original.load()
        crop = select_crop(original, size)
        wallpaper = render_crop(original, crop, size)
        provenance.update(
            source=source.name,
            source_size=list(original.size),
            crop=asdict(crop),
            source_corners=[list(corner) for corner in crop.corners()],
        )

    exif = Image.Exif()
    exif[METADATA_TAG] = json.dumps(provenance, sort_keys=True)
    output.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output, prefix=".getSDO-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            wallpaper.save(handle, format="JPEG", quality=95, subsampling=0, exif=exif)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "Created wallpaper", destination, provenance
