#!/usr/bin/env python3
"""Download one SDO image per observation day and view, optionally crop wallpapers."""

import argparse
import datetime as dt
import http.client
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

SDO_ROOT = "https://sdo.gsfc.nasa.gov"
VIEWS = {
    "aia_131": "0131",
    "aia_171": "0171",
    "aia_193": "0193",
    "aia_211": "0211",
    "aia_304": "0304",
    "aia_335": "0335",
    "aia_1700": "1700",
}
MAX_IMAGE_BYTES = 32 * 1024 * 1024
USER_AGENT = "solar-horizon/2.0 (+https://github.com/mint5auce/solar-horizon)"


def request(url: str, timeout: float):
    return urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout)


def latest_timestamp(channel: str, timeout: float) -> dt.datetime:
    """Read NASA's observation time, rather than the download or file-change time."""
    url = f"{SDO_ROOT}/assets/img/latest/times{channel}.txt"
    with request(url, timeout) as response:
        text = response.read(1024).decode("ascii").strip()
    match = re.fullmatch(rf"{channel}:\s*(\d{{8}}_\d{{6}})", text)
    if not match:
        raise ValueError(f"Invalid observation timestamp from {url}")
    return dt.datetime.strptime(match[1], "%Y%m%d_%H%M%S").replace(
        tzinfo=dt.timezone.utc
    )


def is_jpeg(path: Path) -> bool:
    """Check boundary markers before treating an existing download as complete."""
    if not path.is_file() or path.stat().st_size < 5:
        return False
    with path.open("rb") as image:
        start = image.read(3)
        image.seek(-2, os.SEEK_END)
        end = image.read(2)
    return start == b"\xff\xd8\xff" and end == b"\xff\xd9"


def save_image(url: str, destination: Path, timeout: float) -> None:
    """Reject obvious error/truncated responses and publish the file atomically."""
    with request(url, timeout) as response:
        if response.headers.get_content_type() not in {"image/jpeg", "image/jpg"}:
            raise ValueError(f"Expected a JPEG image from {url}")
        data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(
                f"Image exceeds the {MAX_IMAGE_BYTES // 1024 // 1024} MiB limit"
            )
        length = response.headers.get("Content-Length")
        if length is not None and len(data) != int(length):
            raise ValueError(f"Incomplete image from {url}")
        if not data.startswith(b"\xff\xd8\xff") or not data.endswith(b"\xff\xd9"):
            raise ValueError(f"Invalid or incomplete JPEG from {url}")

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=".solar-horizon-",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_image(
    output: Path,
    view: str,
    timestamp: dt.datetime,
    resolution: int,
    timeout: float,
    force: bool,
) -> tuple[str, Path]:
    channel = VIEWS[view]
    # Keep the original filename format, including the actual observation time.
    filename = f"{timestamp:%Y%m%d_%H%M%S}_{resolution}_{channel}.jpg"
    destination = output / f"{view}_{filename}"
    if not force:
        pattern = f"{view}_{timestamp:%Y%m%d}_*_{resolution}_{channel}.jpg"
        for existing in sorted(output.glob(pattern)):
            if is_jpeg(existing):
                return "Skipped", existing

    # Use the immutable browse image to avoid a race with the updating latest image.
    url = f"{SDO_ROOT}/assets/img/browse/{timestamp:%Y/%m/%d}/{filename}"
    save_image(url, destination, timeout)
    return "Downloaded", destination


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return timeout


def wallpaper_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)[xX](\d+)", value)
    if match:
        width, height = map(int, match.groups())
        if (
            64 <= min(width, height)
            and max(width, height) <= 8192
            and width * height <= 40_000_000
            and max(width, height) / min(width, height) <= 4
        ):
            return width, height
    raise argparse.ArgumentTypeError(
        "wallpaper size must be WIDTHxHEIGHT, 64-8192 pixels per side, "
        "at most 40 megapixels and aspect ratio at most 4:1"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.home() / "Pictures" / "sdo-feed",
        help="destination folder (default: ~/Pictures/sdo-feed)",
    )
    parser.add_argument(
        "--views",
        nargs="+",
        choices=VIEWS,
        default=list(VIEWS),
        help="views to download (default: all seven original views)",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        choices=(512, 1024, 2048, 4096),
        default=4096,
        help="image width and height in pixels (default: 4096)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=30.0,
        help="network timeout in seconds per request (default: 30)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="refresh the latest observation and any wallpaper even if already saved",
    )
    parser.add_argument(
        "--wallpaper",
        type=wallpaper_size,
        metavar="WIDTHxHEIGHT",
        help="also select and crop a plasma wallpaper (requires requirements-wallpaper.txt)",
    )
    parser.add_argument(
        "--wallpaper-output",
        type=Path,
        help="wallpaper folder (default: ~/Library/Caches/Solar Horizon/wallpapers)",
    )
    parser.add_argument(
        "--crop",
        type=Path,
        metavar="IMAGE",
        help="crop an existing full-disc image without network access; requires --wallpaper",
    )
    parser.add_argument(
        "--solar-horizon",
        action="store_true",
        help="refresh the daily AIA 193 Å teal / pewter scene for the native macOS hosts",
    )
    args = parser.parse_args(argv)
    if args.solar_horizon:
        if (
            args.wallpaper
            or args.crop
            or args.wallpaper_output
            or args.resolution != 4096
        ):
            parser.error(
                "--solar-horizon uses a full 4096-pixel source and cannot be combined with cropping"
            )
        try:
            from refresh import refresh

            updated = refresh(
                originals=args.output, force=args.force, timeout=args.timeout
            )
            print(
                "Solar Horizon scene refreshed."
                if updated
                else "Solar Horizon is not due or a refresh is running."
            )
            return 0
        except (ImportError, OSError, ValueError, http.client.HTTPException) as error:
            print(f"Error refreshing Solar Horizon: {error}", file=sys.stderr)
            return 1
    if (args.crop or args.wallpaper_output) and not args.wallpaper:
        parser.error("--crop and --wallpaper-output require --wallpaper WIDTHxHEIGHT")

    if args.wallpaper:
        try:
            from wallpaper import create_wallpaper
        except ImportError as error:
            print(
                "Error: wallpaper mode requires Pillow and NumPy. Install with "
                f"'{sys.executable} -m pip install -r requirements-wallpaper.txt' "
                f"({error}).",
                file=sys.stderr,
            )
            return 1

    output = args.output.expanduser()
    wallpapers = (
        args.wallpaper_output or Path.home() / "Library/Caches/Solar Horizon/wallpapers"
    ).expanduser()

    def crop_image(path: Path) -> None:
        status, target, metadata = create_wallpaper(
            path, wallpapers, args.wallpaper, args.force
        )
        crop = metadata["crop"]
        print(
            f"{status}: {target} "
            f"(source crop {crop['width']:.0f}x{crop['height']:.0f}, "
            f"rotation {crop['angle']} degrees)",
            flush=True,
        )

    if args.crop:
        try:
            crop_image(args.crop.expanduser())
        except (OSError, ValueError) as error:
            print(f"Error creating wallpaper: {error}", file=sys.stderr)
            return 1
        return 0

    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"Error creating output folder {output}: {error}", file=sys.stderr)
        return 1

    now = dt.datetime.now(dt.timezone.utc)
    failures = 0
    for view in dict.fromkeys(args.views):
        try:
            timestamp = latest_timestamp(VIEWS[view], args.timeout)
            age = now - timestamp
            if age > dt.timedelta(days=1):
                print(
                    f"Warning: {view}: NASA's latest observation is "
                    f"{timestamp:%Y-%m-%d %H:%M:%S} UTC "
                    f"({age.total_seconds() / 3600:.1f} hours old).",
                    file=sys.stderr,
                )
            status, path = download_image(
                output, view, timestamp, args.resolution, args.timeout, args.force
            )
            print(f"{status}: {path}", flush=True)
            if args.wallpaper:
                crop_image(path)
        except (OSError, ValueError, http.client.HTTPException) as error:
            print(f"Error: {view}: {error}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
