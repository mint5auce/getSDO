#!/usr/bin/env python3
"""Download one SDO image per observation day and view, without dependencies."""

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
USER_AGENT = "getSDO/2.0 (+https://github.com/mint5auce/getSDO)"


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
            dir=destination.parent, prefix=".getSDO-", suffix=".tmp", delete=False
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
        help="download the latest observation even if this observation day is saved",
    )
    args = parser.parse_args(argv)
    output = args.output.expanduser()
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
