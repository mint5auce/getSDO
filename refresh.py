"""One bounded daily refresh; launchd and the app trigger overdue retries."""

import argparse
import ctypes
import datetime as dt
import fcntl
import json
import logging
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

import solar_horizon
from solar_scene import (
    SUPPORT,
    atomic_json,
    prepare_scene,
    prune_scenes,
    separate_paths,
    validate_image,
)

logger = logging.getLogger(__name__)


def continuous_seconds():
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    lib.clock_gettime_nsec_np.argtypes = [ctypes.c_uint]
    lib.clock_gettime_nsec_np.restype = ctypes.c_uint64
    return (
        lib.clock_gettime_nsec_np(4) / 1e9
    )  # CLOCK_MONOTONIC_RAW includes sleep on macOS.


def due(state, now, force=False):
    if force:
        return True
    day = now.date() if now.hour >= 8 else now.date() - dt.timedelta(days=1)
    if state.get("completed_day") != day.isoformat():
        return True
    return bool(state.get("next_attempt") and now.timestamp() >= state["next_attempt"])


def refresh(support=SUPPORT, originals=None, force=False, now=None, timeout=30):
    support = Path(support).expanduser()
    config_path = support / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    originals = Path(
        originals or config.get("originals", Path.home() / "Pictures/sdo-feed")
    ).expanduser()
    separate_paths(originals, support)
    support.mkdir(parents=True, exist_ok=True)
    # Nonblocking exclusive lock covers network, scene publication and state updates.
    with (support / "refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        state_path = support / "refresh-state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        now = now or dt.datetime.now().astimezone()
        if not due(state, now, force):
            return False
        day = (
            now.date() if now.hour >= 8 else now.date() - dt.timedelta(days=1)
        ).isoformat()
        if state.get("retry_day") != day:
            state["retry"] = 0
        try:
            stamp = solar_horizon.latest_timestamp("0193", timeout)
            scene_path = support / "scene.json"
            old = json.loads(scene_path.read_text()) if scene_path.exists() else None
            active_observation = (
                old.get("current", {}).get("observation") if old else None
            )
            if (
                active_observation
                and dt.datetime.fromisoformat(active_observation) > stamp
            ):
                raise ValueError(
                    "NASA reports an older observation; retaining the newer active scene"
                )
            name = f"aia_193_{stamp:%Y%m%d_%H%M%S}_4096_0193.jpg"
            url = f"{solar_horizon.SDO_ROOT}/assets/img/browse/{stamp:%Y/%m/%d}/{stamp:%Y%m%d_%H%M%S}_4096_0193.jpg"
            originals.mkdir(parents=True, exist_ok=True)
            source = originals / name
            if source.exists():
                validate_image(source)
            else:
                # Sibling staging keeps the atomic rename on the same volume, outside originals.
                with tempfile.TemporaryDirectory(
                    prefix=".solar-horizon-stage-", dir=originals.parent
                ) as staging:
                    staged = Path(staging) / name
                    solar_horizon.save_image(url, staged, timeout)
                    validate_image(staged)
                    staged.replace(source)
            manifest = prepare_scene(source, support, stamp.isoformat(), url)
            if not old or old["current"]["id"] != manifest["id"]:
                atomic_json(
                    scene_path,
                    {
                        "schema": 1,
                        "current": manifest,
                        "previous": old["current"] if old else None,
                        "transition_start": continuous_seconds(),
                        "transition_seconds": 10,
                    },
                )
            prune_scenes(support, json.loads(scene_path.read_text()))
            age = (now.astimezone(dt.timezone.utc) - stamp).total_seconds()
            stale = age > 86400
            retry = state.get("retry", 0) if stale else 0
            delays = [1800, 7200, 21600]
            state = {
                "completed_day": day,
                "retry_day": day,
                "checked_at": now.isoformat(),
                "observation": stamp.isoformat(),
                "status": "NASA source stale; retaining latest available observation"
                if stale
                else "Up to date",
                "retry": min(retry + 1, 3) if stale else 0,
                "next_attempt": now.timestamp() + delays[retry]
                if stale and retry < 3
                else None,
            }
            logger.info("%s: %s", state["status"], stamp.isoformat())
        except Exception as error:
            retry = state.get("retry", 0)
            state.update(
                status=f"Refresh failed: {error}",
                checked_at=now.isoformat(),
                retry=min(3, retry + 1),
                next_attempt=now.timestamp() + [1800, 7200, 21600][retry]
                if retry < 3
                else None,
                completed_day=day,
                retry_day=day,
            )
            atomic_json(state_path, state)
            logger.exception("Refresh failed; active scene unchanged")
            raise
        atomic_json(state_path, state)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support", type=Path, default=SUPPORT)
    parser.add_argument("--originals", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    logs = Path.home() / "Library/Logs/Solar Horizon"
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            RotatingFileHandler(
                logs / "refresh.log", maxBytes=1_000_000, backupCount=3
            ),
            logging.StreamHandler(),
        ],
    )
    try:
        refresh(args.support, args.originals, args.force)
    except Exception:
        logger.exception("Refresh command failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
