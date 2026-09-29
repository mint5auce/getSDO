# Contributing

Run commands from the repository root.

## Python tests and lint

Run the downloader tests without third-party packages:

```sh
python3 -m unittest discover -s tests -p test_solar_horizon.py -v
```

Tests use a local HTTP server and temporary directories, so they do not need internet access or write to your Pictures folder.
They exercise the real CLI, repeat runs, stale observations, invalid responses, partial failures, and safe writes.
Wallpaper tests also check selection against a known moving feature, rotation geometry, exclusion of the limb and footer, portrait and ultrawide layouts, source preservation, provenance and cache repair.
Image-dependent downloader tests are skipped when the optional packages are absent.
The complete suite also covers scene publication, daily retries, owned-bundle replacement and isolated upscale failure retention, and requires Pillow and NumPy.
Create a development environment and run the complete suite:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Then run lint and formatting checks:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
xcrun swift-format lint --strict macOS/*.swift scripts/upscale-poc-render.swift
```

The Swift check and `scripts/validate-macos.sh` require macOS and Xcode.
For a live smoke test without touching your screensaver collection:

```sh
python3 solar_horizon.py --output /tmp/solar-horizon-smoke --resolution 512
```

## Native validation

With the development environment above and a prepared Solar Horizon scene:

```sh
scripts/validate-macos.sh
```

The native check captures Metal and packaged screensaver frames at quarter turns, checks exact loop endpoints for both, and compares geometry with a small allowance for colour interpolation differences.
It also reproduces Retina frame and bounds changes, checks five screensaver detach/start/stop cycles and the desktop Metal renderer's 10-second crossfade in linear light.
Surface Scroll checks compare the rendered output against native source crops, verify whole-image coverage for landscape, portrait and large displays, and check seamless endpoints and pause continuity.
Solar Peek checks compare native-scale inverse rotation against the source, reference framing, desktop/screensaver agreement, loop endpoints and preview restarts.
The screensaver uses AppKit compositing for its observation fade; its fade is not asserted to be pixel-identical to Metal.
Capture artifacts are written under the ignored `build/validation` directory.
Native renderer validation requires a prepared scene at the standard application-support location; install and refresh Solar Horizon first.
For a full-period process soak with the app already running, use `.venv/bin/python scripts/soak.py`.
The soak records process continuity, CPU and resident memory; it does not measure GPU power or prove a system-host lock/unlock transition.
See the [validation record](docs/solar-horizon-validation.md) for real System Settings preview checks and remaining battery, multi-display, sleep/wake and lock/unlock checks.
