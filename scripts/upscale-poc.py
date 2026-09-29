#!/usr/bin/env python3
"""Isolated, local Solar Horizon upscale experiment; never publishes a live scene."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "build/solar-horizon-upscale-poc"
SUPPORT = Path.home() / "Library/Application Support/getSDO"
BACKEND = "20251207-174704"
ARCHIVE = "277419791281a56eae0c739c70120b974d7267cf7c2de8e86dc09798d4b314db"
WEIGHTS_ARCHIVE = "e0ad05580abfeb25f8d8fb55aaf7bedf552c375b5b4d9bd3c8d59764d2cc333a"
MODEL_HASHES = {
    "realesrgan-x4plus.bin": "713ee713b0353afaa27976f0563a64a5043bd70b9bd8936c2e26e25ebcdbcddf",
    "realesrgan-x4plus.param": "35330ececcea33b6c397a72548e788d5d53becee4734c50b7fada36e89f10a86",
}
VARIANTS = {
    "A": "Current 4096",
    "B": "Lanczos + mild sharpening",
    "C": "Real-ESRGAN 4x to 2x",
}
Image.MAX_IMAGE_PIXELS = 300_000_000


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_image(image, path):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp.png")
    try:
        image.save(temporary, format="PNG")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def download(url, path, expected):
    if path.exists() and digest(path) == expected:
        return
    temporary = path.with_suffix(".download")
    try:
        print(f"Downloading official artifact: {path.name}", flush=True)
        with (
            urllib.request.urlopen(url, timeout=60) as response,
            temporary.open("wb") as stream,
        ):
            shutil.copyfileobj(response, stream)
        if digest(temporary) != expected:
            raise ValueError(f"Downloaded artifact hash mismatch: {path}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def setup(root):
    for name in ("downloads", "models", "tools", "cache", "runs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    archive = root / "downloads/upscayl-macos.zip"
    download(
        f"https://github.com/upscayl/upscayl-ncnn/releases/download/{BACKEND}/upscayl-bin-{BACKEND}-macos.zip",
        archive,
        ARCHIVE,
    )
    binary = root / f"tools/upscayl-bin-{BACKEND}-macos/upscayl-bin"
    # Extract named files only. Never follow archive paths or symlinks.
    with zipfile.ZipFile(archive) as package:
        for name in ("upscayl-bin", "LICENSE", "README.md"):
            target = binary.parent / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = package.read(f"upscayl-bin-{BACKEND}-macos/{name}")
            if not target.exists() or target.read_bytes() != content:
                target.write_bytes(content)
    binary.chmod(0o755)
    weights = root / "downloads/upstream-models.zip"
    download(
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip",
        weights,
        WEIGHTS_ARCHIVE,
    )
    with zipfile.ZipFile(weights) as package:
        for name, expected in MODEL_HASHES.items():
            target = root / "models" / name
            content = package.read(f"models/{name}")
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Model hash mismatch")
            if not target.exists() or digest(target) != expected:
                target.write_bytes(content)
    return binary


def protected_files(manifest):
    roots = [
        Path(manifest["source"]).parent,
        Path.home() / "Applications/Solar Horizon.app",
        Path.home() / "Library/Screen Savers/Solar Horizon.saver",
    ]
    files = [
        SUPPORT / "scene.json",
        SUPPORT / "playback.json",
        Path(manifest["texture"]),
    ]
    files += list((Path.home() / "Library/LaunchAgents").glob("*getSDO*.plist"))
    files += [
        p for root in roots if root.exists() for p in root.rglob("*") if p.is_file()
    ]
    return {str(p): digest(p) for p in files if p.is_file()}


def infer(root, binary, manifest, tile):
    settings = {
        "source_sha256": manifest["sha256"],
        "backend": BACKEND,
        "backend_sha256": digest(binary),
        "models": MODEL_HASHES,
        "model_scale": 4,
        "output_scale": 2,
        "tile": tile,
        "threads": "1:1:1",
        "gpu": 0,
        "tta": False,
        "downsample": "Upscayl stb_image_resize2 sRGB default filter",
    }
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    destination = root / "cache" / key
    if (destination / "inference.json").exists():
        recorded = json.loads((destination / "inference.json").read_text())
        image = destination / "full-disc-8192.png"
        if recorded["output_sha256"] == digest(image):
            with Image.open(image) as cached:
                cached.verify()
                if cached.size != (8192, 8192):
                    raise ValueError("Cached inference dimensions differ")
            print("Reusing verified completed inference", flush=True)
            return image, recorded, True
        raise ValueError("Inference cache hash mismatch; valid outputs left intact")
    # A new directory is published only after every check succeeds.
    with tempfile.TemporaryDirectory(
        prefix=".inference-", dir=root / "cache"
    ) as folder:
        stage = Path(folder)
        output = stage / "full-disc-8192.png"
        command = [
            str(binary),
            "-i",
            manifest["source"],
            "-o",
            str(output),
            "-m",
            str(root / "models"),
            "-n",
            "realesrgan-x4plus",
            "-z",
            "4",
            "-s",
            "2",
            "-t",
            str(tile),
            "-j",
            "1:1:1",
            "-g",
            "0",
            "-f",
            "png",
        ]
        print(
            f"Running local 4x inference with {tile}px tiles, then 2x output",
            flush=True,
        )
        started = time.perf_counter()
        with (stage / "process.log").open("w") as log:
            subprocess.run(
                ["/usr/bin/time", "-l", *command], stdout=log, stderr=log, check=True
            )
        elapsed = time.perf_counter() - started
        with Image.open(output) as image:
            image.verify()
            if image.size != (8192, 8192):
                raise ValueError("Backend returned unexpected output dimensions")
        if digest(manifest["source"]) != manifest["sha256"]:
            raise ValueError("Source changed while processing")
        log = (stage / "process.log").read_text()
        memory = {}
        for label in ("maximum resident set size", "peak memory footprint"):
            match = re.search(r"(\d+)\s+" + label, log)
            memory[label.replace(" ", "_") + "_bytes"] = (
                int(match[1]) if match else None
            )
        recorded = dict(
            settings,
            tile_pad_input_pixels=10,
            command=command,
            elapsed_seconds=elapsed,
            output_dimensions=[8192, 8192],
            output_sha256=digest(output),
            measured_memory=memory,
            backend_licence="AGPL-3.0",
            model_licence="BSD-3-Clause",
            model="RealESRGAN_x4plus / RRDBNet-23 photographic restoration",
        )
        atomic_json(stage / "inference.json", recorded)
        # Rename the whole completed cache entry atomically, including provenance.
        stage.rename(destination)
    return destination / "full-disc-8192.png", recorded, False


def grade_parameters(manifest):
    with Image.open(manifest["source"]) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
    gray = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    n = len(gray)
    yy, xx = np.ogrid[:n, :n]
    radius = np.hypot(
        xx.astype(np.float32) - (n - 1) / 2, yy.astype(np.float32) - (n - 1) / 2
    ) / (manifest["limb_uv"] * n)
    low, high = map(float, np.percentile(gray[radius < 0.98], [1, 99.8]))
    return {"low": low, "high": high, "limb_uv": manifest["limb_uv"], "gamma": 1.15}


def grade(image, params):
    # Row chunks cap RAM. Identical original-derived stretch and normalized mask.
    n = image.width
    output = np.empty((n, n, 3), dtype=np.uint8)
    xx = np.arange(n, dtype=np.float32)[None, :] - (n - 1) / 2
    shadows = np.array([0.025, 0.085, 0.095], dtype=np.float32)
    mids = np.array([0.17, 0.29, 0.30], dtype=np.float32)
    pewter = np.array([0.78, 0.77, 0.70], dtype=np.float32)
    for y in range(0, n, 128):
        end = min(y + 128, n)
        rgb = (
            np.asarray(image.crop((0, y, n, end)).convert("RGB"), dtype=np.float32)
            / 255
        )
        gray = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        yy = np.arange(y, end, dtype=np.float32)[:, None] - (n - 1) / 2
        radius = np.hypot(xx, yy) / (params["limb_uv"] * n)
        mask = np.clip((1.13 - radius) / 0.06, 0, 1)
        mask *= np.clip((0.45 * n - radius * params["limb_uv"] * n) / (n * 0.02), 0, 1)
        t = (
            np.clip(
                (gray - params["low"]) / max(0.01, params["high"] - params["low"]), 0, 1
            )
            ** 1.15
        )[..., None]
        colour = np.where(
            t < 0.55,
            shadows + (mids - shadows) * t / 0.55,
            mids + (pewter - mids) * (t - 0.55) / 0.45,
        )
        gain = 1 - 0.42 * np.clip((radius - 1) / 0.08, 0, 1)
        colour *= (mask * gain)[..., None]
        output[y:end] = (np.clip(colour, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(output)


def prepare_variants(folder, manifest, ai):
    params = grade_parameters(manifest)
    for variant in VARIANTS:
        (folder / "scenes" / variant).mkdir(parents=True)
    # A is the exact active PNG, including all current grading quantization.
    shutil.copyfile(manifest["texture"], folder / "scenes/A/texture.png")
    with Image.open(manifest["source"]) as original:
        reconstructed = grade(original, params)
        with Image.open(manifest["texture"]) as active:
            difference = np.abs(
                np.asarray(reconstructed, dtype=np.int16)
                - np.asarray(active.convert("RGB"), dtype=np.int16)
            )
            if difference.max() > 1 or np.count_nonzero(difference) > 1000:
                raise ValueError(
                    "PoC grade differs materially from the current texture"
                )
        enlarged = original.convert("RGB").resize(
            (8192, 8192), Image.Resampling.LANCZOS
        )
        # Conservative unsharp mask: 20%, radius 0.8 output pixels, 2/255 threshold.
        enlarged = enlarged.filter(
            ImageFilter.UnsharpMask(radius=0.8, percent=20, threshold=2)
        )
        atomic_image(grade(enlarged, params), folder / "scenes/B/texture.png")
    with Image.open(ai) as image:
        atomic_image(grade(image, params), folder / "scenes/C/texture.png")
    return params


def render(folder, manifest, root, animate):
    binary = root / "tools/solar-poc-render"
    subprocess.run(
        [
            "xcrun",
            "swiftc",
            "-O",
            str(REPO / "macOS/SolarSceneCore.swift"),
            str(REPO / "scripts/upscale-poc-render.swift"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    display = json.loads(subprocess.check_output([str(binary), "display"], text=True))
    atomic_json(folder / "display.json", display)
    width, height = display["width"], display["height"]
    jobs = []
    # Eight horizon phases jointly cover the full outer band; closure also checked.
    for variant in VARIANTS:
        for seconds in (*range(0, 1200, 150), 1200):
            jobs.append(
                {
                    "variant": variant,
                    "seconds": seconds,
                    "output": f"frames/{variant}-{seconds:04}.png",
                }
            )
        if animate:
            jobs.append(
                {
                    "variant": variant,
                    "seconds": 600,
                    "duration": 12,
                    "speed": 1,
                    "fps": 30,
                    "output": f"animation/{variant}-real-speed.mp4",
                }
            )
            jobs.append(
                {
                    "variant": variant,
                    "seconds": 0,
                    "duration": 20,
                    "speed": 60,
                    "fps": 30,
                    "output": f"animation/{variant}-60x-inspection.mp4",
                }
            )
    atomic_json(
        folder / "render-jobs.json",
        {
            "width": width,
            "height": height,
            "limb_uv": manifest["limb_uv"],
            "jobs": jobs,
        },
    )
    subprocess.run([str(binary), str(folder)], check=True)
    return display


def crops_and_checks(folder):
    crops = {
        "loops": {"phase": 300, "box": (1800, 960, 2280, 1280)},
        "quiet": {"phase": 600, "box": (700, 1100, 1180, 1420)},
        "dark-boundary": {"phase": 600, "box": (1500, 1450, 1980, 1770)},
        "limb": {"phase": 300, "box": (1060, 840, 1540, 1160)},
    }
    results = {}
    for variant in VARIANTS:
        for name, spec in crops.items():
            with Image.open(
                folder / f"frames/{variant}-{spec['phase']:04}.png"
            ) as frame:
                atomic_image(
                    frame.crop(spec["box"]),
                    folder / "details" / f"{variant}-{name}.png",
                )
        # Outer band crops are at backing-pixel scale, not enlarged source pixels.
        for seconds in range(0, 1200, 150):
            with Image.open(folder / f"frames/{variant}-{seconds:04}.png") as frame:
                atomic_image(
                    frame.crop((1220, 830, 1700, 1310)),
                    folder / "details" / f"{variant}-band-{seconds:04}.png",
                )
        with (
            Image.open(folder / f"frames/{variant}-0000.png") as first,
            Image.open(folder / f"frames/{variant}-1200.png") as last,
        ):
            a, b = np.asarray(first.convert("RGB")), np.asarray(last.convert("RGB"))
            results[variant] = {
                "rotation_closure_identical": bool(np.array_equal(a, b)),
                "black_sky_top_200_rows_max": int(a[:200].max()),
            }
    atomic_json(folder / "checks.json", {"variants": results, "crops_2940x1912": crops})
    return results


def tile_seam_check(path):
    """Compare every 512px output tile join with nearby gradients in the raw AI image."""
    scores = {"vertical": [], "horizontal": []}
    with Image.open(path) as image:
        for edge in range(512, 8192, 512):
            strip = np.asarray(
                image.crop((edge - 5, 1000, edge + 5, 7000)), dtype=np.int16
            )
            gradients = np.abs(strip[:, 1:] - strip[:, :-1]).mean(axis=(0, 2))
            baseline = float(np.median(np.r_[gradients[:3], gradients[5:]]))
            scores["vertical"].append(
                {"edge": edge, "ratio": float(gradients[4] / max(0.01, baseline))}
            )
            strip = np.asarray(
                image.crop((1000, edge - 5, 7000, edge + 5)), dtype=np.int16
            )
            gradients = np.abs(strip[1:] - strip[:-1]).mean(axis=(1, 2))
            baseline = float(np.median(np.r_[gradients[:3], gradients[5:]]))
            scores["horizontal"].append(
                {"edge": edge, "ratio": float(gradients[4] / max(0.01, baseline))}
            )
    return scores


def automated_report(folder, provenance):
    inference = provenance["inference"]
    display = provenance["display"]
    checks = provenance["checks"]
    memory = inference["measured_memory"]
    lines = [
        "# Solar Horizon upscale comparison",
        "",
        "This is an automatically generated measurement summary; human visual judgement is still required.",
        "Open [the comparison](index.html) to review all three variants and the real-speed motion clips.",
        "",
        f"Source: `{provenance['source']['source']}`.",
        f"Source SHA-256: `{provenance['source']['sha256']}`.",
        f"Backend release: Upscayl NCNN `{BACKEND}`.",
        "Model: upstream photographic RealESRGAN-x4plus at native 4x, resized by the backend to 2x.",
        f"Measured inference: {inference['elapsed_seconds']:.1f} seconds, {memory['peak_memory_footprint_bytes'] / 1e9:.2f} GB peak memory footprint.",
        f"Display backing resolution: {display['width']} x {display['height']} pixels.",
        "",
        "The current 4,096-pixel texture is compared with Lanczos plus mild sharpening and Real-ESRGAN at 8,192 pixels.",
        "The original-derived colour stretch, teal/pewter grade, footer mask, horizon geometry and static glow are shared.",
        "Eight 45-degree phases and the 1,200-second seam were rendered with the production Metal shader.",
        f"Exact rotation closure by variant: {', '.join(f'{name}={result['rotation_closure_identical']}' for name, result in checks.items())}.",
        "",
        "No live wallpaper, screensaver or daily pipeline was changed.",
        "AI detail is a visual reconstruction, not recovered scientific evidence.",
        "The black screensaver preview is outside this comparison.",
        "",
        "See [provenance](provenance.json), [Metal allocations](metal-measurements.json) and the [pinned scene](scene-snapshot.json).",
    ]
    # Leave a simple report even if the user reruns this PoC on a later observation.
    (folder / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=SUPPORT / "scene.json")
    parser.add_argument("--output", type=Path, default=ROOT)
    parser.add_argument("--stage", choices=["infer", "all"], default="all")
    parser.add_argument("--tile", type=int, default=256)
    parser.add_argument("--no-animation", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.scene.read_text())["current"]
    root = args.output.expanduser().resolve()
    original_dir = Path(manifest["source"]).resolve().parent
    for protected in (original_dir, SUPPORT.resolve()):
        if (
            root == protected
            or root.is_relative_to(protected)
            or protected.is_relative_to(root)
        ):
            raise ValueError("PoC output overlaps originals or live support")
    if (
        manifest["profile"] != "teal-pewter-v3"
        or digest(manifest["source"]) != manifest["sha256"]
    ):
        raise ValueError("Expected the verified active teal-pewter-v3 source")
    with Image.open(manifest["source"]) as image:
        if image.size != (4096, 4096):
            raise ValueError(
                "This controlled experiment requires the active 4096 source"
            )
    if args.tile < 32:
        raise ValueError("Tile must be at least 32")
    root.mkdir(parents=True, exist_ok=True)
    before = protected_files(manifest)
    binary = setup(root)
    ai, inference, cached = infer(root, binary, manifest, args.tile)
    if args.stage == "infer":
        atomic_json(
            root / "last-inference.json", {"cache": str(ai), "record": inference}
        )
        if protected_files(manifest) != before:
            raise ValueError("Protected files changed during the experiment")
        print(ai)
        return
    started = time.perf_counter()
    run_id = f"{manifest['sha256'][:12]}-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    destination = root / "runs" / run_id
    with tempfile.TemporaryDirectory(prefix=".render-", dir=root / "runs") as temporary:
        folder = Path(temporary)
        for name in ("frames", "details", "animation"):
            (folder / name).mkdir()
        params = prepare_variants(folder, manifest, ai)
        display = render(folder, manifest, root, not args.no_animation)
        checks = crops_and_checks(folder)
        after = protected_files(manifest)
        if before != after:
            raise ValueError("Protected files changed; comparison was not published")
        frozen_scene = dict(manifest)
        frozen_scene["texture"] = str(destination / "scenes/A/texture.png")
        atomic_json(folder / "scene-snapshot.json", {"current": frozen_scene})
        shutil.copyfile(REPO / "scripts/upscale-poc-viewer.html", folder / "index.html")
        provenance = {
            "source": manifest,
            "inference": inference,
            "inference_cache_hit": cached,
            "grade": params,
            "display": display,
            "checks": checks,
            "raw_ai_tile_seams": tile_seam_check(ai),
            "render_core_sha256": digest(REPO / "macOS/SolarSceneCore.swift"),
            "render_binary_sha256": digest(root / "tools/solar-poc-render"),
            "preparation_sha256": digest(REPO / "solar_scene.py"),
            "python_dependencies": {
                "pillow": Image.__version__,
                "numpy": np.__version__,
            },
            "ffmpeg_version": subprocess.check_output(
                ["ffmpeg", "-version"], text=True
            ).splitlines()[0],
            "review_elapsed_seconds": time.perf_counter() - started,
            "protected_files_unchanged": True,
            "protected_files": before,
            "output_hashes": {
                str(p.relative_to(folder)): digest(p)
                for p in folder.rglob("*")
                if p.is_file()
            },
            "order": "Original RGB upscale once; original-derived fixed intensity stretch; teal/pewter grade; normalized corona/footer mask; native Metal horizon sampling",
            "control_B": "Pillow Lanczos 2x then UnsharpMask(radius=0.8, percent=20, threshold=2), before identical grading",
        }
        automated_report(folder, provenance)
        provenance["output_hashes"]["report.md"] = digest(folder / "report.md")
        atomic_json(folder / "provenance.json", provenance)
        folder.rename(destination)
    atomic_json(
        root / "latest.json",
        {"run": str(destination), "index": str(destination / "index.html")},
    )
    print(destination / "index.html", flush=True)


if __name__ == "__main__":
    main()
