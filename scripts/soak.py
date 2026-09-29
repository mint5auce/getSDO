"""Observe the running desktop for a full period without synthesising input."""

import json
import subprocess
import time
from pathlib import Path

samples = []
start = time.monotonic()
while True:
    elapsed = time.monotonic() - start
    result = subprocess.run(
        ["ps", "-axo", "pid,%cpu,rss,command"],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = [
        line.strip()
        for line in result.stdout.splitlines()
        if "/Applications/Solar Horizon.app/Contents/MacOS/SolarHorizon" in line
    ]
    if not rows:
        raise RuntimeError("Desktop exited during soak")
    samples.append({"elapsed": round(elapsed, 3), "processes": rows})
    Path("build/soak.json").write_text(json.dumps(samples, indent=2) + "\n")
    if elapsed >= 1200:
        break
    time.sleep(min(30, 1200 - elapsed))
print(f"20-minute process soak complete: {len(samples)} samples")
