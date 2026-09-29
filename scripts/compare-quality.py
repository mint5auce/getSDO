#!/usr/bin/env python3
"""Render review-only JPEG and FITS comparisons without publishing an active scene."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates


def linear(rgb):
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def srgb(rgb):
    rgb = np.clip(rgb, 0, 1)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - 0.055)


def coordinates(size, seconds):
    width, height = size
    yy, xx = np.mgrid[:height, :width].astype(np.float32)
    radius = max(width, 1.16 * height)
    x = (xx + 0.5 - width / 2) / radius
    y = (yy + 0.5 - (0.48 * height + radius)) / radius
    angle = seconds % 1200 / 1200 * math.tau
    return x * math.cos(angle) + y * math.sin(angle), -x * math.sin(
        angle
    ) + y * math.cos(angle)


def sample(values, x, y, order):
    return map_coordinates(values, [y, x], order=order, mode="constant", cval=0)


def sharpen(rgb):
    # A small luminance-only correction avoids coloured fringes and bright halos.
    luminance = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    detail = luminance - gaussian_filter(luminance, 0.8)
    correction = np.where(np.abs(detail) > 0.002, detail * 0.25, 0)
    return np.clip(rgb + correction[..., None], 0, 1)


def jpeg_frame(manifest, x, y, improved):
    with Image.open(manifest["texture"]) as image:
        pixels = linear(np.asarray(image, dtype=np.float32) / 255)
    sx = (0.5 + x * manifest["limb_uv"]) * pixels.shape[1] - 0.5
    sy = (0.5 + y * manifest["limb_uv"]) * pixels.shape[0] - 0.5
    rgb = np.stack(
        [sample(pixels[..., c], sx, sy, 3 if improved else 1) for c in range(3)],
        axis=-1,
    )
    return srgb(sharpen(rgb) if improved else rgb)


def fits_frame(path, x, y):
    with fits.open(path) as hdus:
        hdu = next(h for h in hdus if h.data is not None and h.data.ndim == 2)
        header = hdu.header.copy()
        intensity = np.flipud(hdu.data.astype(np.float32)) / header["EXPTIME"]
    if (
        intensity.shape != (4096, 4096)
        or header["WAVELNTH"] != 193
        or header["QUALITY"] != 0
    ):
        raise ValueError("Expected a complete, good-quality 4096px AIA 193 observation")
    centre_x = header["CRPIX1"] - 1
    centre_y = intensity.shape[0] - header["CRPIX2"]
    radius = header["RSUN_OBS"] / abs(header["CDELT1"])
    # Level 1 geometry is read from the FITS header, including north orientation.
    roll = math.radians(header["CROTA2"])
    sx = centre_x + radius * (x * math.cos(roll) + y * math.sin(roll))
    sy = centre_y + radius * (-x * math.sin(roll) + y * math.cos(roll))
    yy, xx = np.ogrid[:4096, :4096]
    disc = np.hypot(xx - centre_x, yy - centre_y) < radius * 0.98
    low, high = np.percentile(intensity[disc], [1, 99.8])
    scaled = np.clip((intensity - low) / max(1, high - low), 0, 1)
    display = (np.arcsinh(50 * scaled) / np.arcsinh(50)) ** 1.15
    luminance = np.clip(sample(display.astype(np.float32), sx, sy, 3), 0, 1)
    shadows = np.array([0.025, 0.085, 0.095], dtype=np.float32)
    mids = np.array([0.17, 0.29, 0.30], dtype=np.float32)
    pewter = np.array([0.78, 0.77, 0.70], dtype=np.float32)
    t = luminance[..., None]
    colour = np.where(
        t < 0.55,
        shadows + (mids - shadows) * t / 0.55,
        mids + (pewter - mids) * (t - 0.55) / 0.45,
    )
    distance = np.hypot(x, y)
    mask = np.clip((1.13 - distance) / 0.06, 0, 1)
    gain = 1 - 0.42 * np.clip((distance - 1) / 0.08, 0, 1)
    colour *= (mask * gain)[..., None]
    metadata = {
        key: header.get(key)
        for key in [
            "T_OBS",
            "DATE-OBS",
            "EXPTIME",
            "QUALITY",
            "WAVELNTH",
            "LVL_NUM",
            "CRPIX1",
            "CRPIX2",
            "CDELT1",
            "CROTA2",
            "RSUN_OBS",
        ]
    }
    metadata.update(
        stretch="asinh(50 * percentile-normalized DN/s), gamma 1.15",
        processing="Header-based centre, plate scale and roll; cubic sampling; mild luminance sharpening; display grade only, not Level 1.5 scientific calibration",
    )
    return srgb(sharpen(linear(colour))), metadata


def save(rgb, path):
    image = Image.fromarray((np.clip(rgb, 0, 1) * 255).round().astype("uint8"))
    image.save(path)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fits", type=Path, required=True)
    parser.add_argument(
        "--scene",
        type=Path,
        default=Path.home() / "Library/Application Support/getSDO/scene.json",
    )
    parser.add_argument("--output", type=Path, default=Path("build/quality-comparison"))
    args = parser.parse_args()
    manifest = json.loads(args.scene.read_text())["current"]
    args.output.mkdir(parents=True, exist_ok=True)
    size, seconds = (2940, 1912), 600
    x, y = coordinates(size, seconds)
    fits_rgb, metadata = fits_frame(args.fits, x, y)
    variants = {
        "baseline": jpeg_frame(manifest, x, y, False),
        "improved-jpeg": jpeg_frame(manifest, x, y, True),
        "scientific-fits": fits_rgb,
    }
    for name, rgb in variants.items():
        image = save(rgb, args.output / f"{name}.png")
        image.crop((1110, 1190, 1830, 1630)).save(args.output / f"{name}-detail.png")
    metadata.update(
        source_url="http://jsoc.stanford.edu/SUM91/D2041276706/S00000/image_lev1.fits",
        source_sha256=hashlib.sha256(args.fits.read_bytes()).hexdigest(),
        jpeg_sha256=manifest["sha256"],
        size=size,
        seconds=seconds,
        source_resolution=4096,
        applied_to_daily_pipeline=False,
    )
    (args.output / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    labels = [
        ("baseline", "Current sampling"),
        ("improved-jpeg", "Cubic JPEG"),
        ("scientific-fits", "Scientific FITS"),
    ]
    buttons = "".join(
        f'<button data-variant="{key}" aria-pressed="{str(i == 1).lower()}">{label}</button>'
        for i, (key, label) in enumerate(labels)
    )
    html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Solar Horizon quality comparison</title>
<style>body{margin:0;background:#101a1d;color:#e0e5e3;font:16px system-ui}main{max-width:1100px;margin:40px auto;padding:0 24px}h1{font-size:28px;font-weight:500}p{color:#a5b8b9;line-height:1.6}nav{display:flex;gap:8px;margin:24px 0;flex-wrap:wrap}button{font:inherit;border:1px solid #496065;background:transparent;color:inherit;padding:10px 16px;border-radius:6px;cursor:pointer}button[aria-pressed=true]{background:#d0d9d3;color:#101a1d}#scene{width:100%;display:block}#detail{display:block;width:720px;max-width:100%;image-rendering:auto}figcaption{margin:12px 0 24px;color:#a5b8b9}figure{margin:0}.link{color:#d0d9d3}button:focus-visible{outline:3px solid #93c9c9;outline-offset:3px}</style>
<main><h1>Solar Horizon · detail comparison</h1><p>The same 21 September observation, horizon and 180° rotation phase. Full frames are 2,940 × 1,912 pixels. These are review samples; your daily pipeline is unchanged. No meaningful sharpness improvement has been established.</p><nav>BUTTONS</nav><figure><img id="scene" src="improved-jpeg.png" alt="Teal and pewter solar horizon"><figcaption id="caption">Cubic JPEG · visually negligible change</figcaption></figure><h2>Detail at output resolution</h2><p>720 × 440 crop. For a strict one-to-one pixel check, open the PNG at 100%.</p><img id="detail" src="improved-jpeg-detail.png" alt="Solar texture detail"><p><a class="link" id="download" href="improved-jpeg.png">Open full-resolution PNG</a> · <a class="link" href="provenance.json">Source and processing details</a></p><p>FITS uses the original Level 1 intensity data, exposure normalization, header geometry and an asinh display stretch. Colour and contrast therefore differ from the rendered JPEG.</p><h2>Five native menu-bar icons</h2><p>SF Symbols rendered at menu-bar size on light and dark backgrounds. Selected and installed: 3, Corona (sun.haze).</p><img style="width:100%;max-width:1000px" src="menu-bar-icons.png" alt="Five native icon choices: Sun, Horizon, Corona, Duotone disc and Rotating ring"><p><a class="link" href="menu-bar-icons.png">Open icon comparison</a></p></main>
<script>const captions={'baseline':'Current sampling · bilinear in linear light','improved-jpeg':'Cubic JPEG · visually negligible change','scientific-fits':'Scientific FITS · original intensity data, cubic sampling, restrained sharpening'};document.querySelectorAll('button').forEach(b=>b.onclick=()=>{document.querySelectorAll('button').forEach(o=>o.setAttribute('aria-pressed',String(o===b)));const k=b.dataset.variant;document.querySelector('#scene').src=k+'.png';document.querySelector('#detail').src=k+'-detail.png';document.querySelector('#download').href=k+'.png';document.querySelector('#caption').textContent=captions[k]});</script></html>""".replace(
        "BUTTONS", buttons
    )
    (args.output / "index.html").write_text(html)
    print(args.output.resolve() / "index.html")


if __name__ == "__main__":
    main()
