# getSDO

Download the latest available solar images from NASA's Solar Dynamics Observatory, create plasma wallpapers, or run Solar Horizon as a macOS desktop and screensaver.
Requires Python 3.11 or newer and an internet connection for downloads.
Download-only mode has no third-party Python dependencies; wallpaper cropping and Solar Horizon scene preparation use Pillow and NumPy.

| Available now | What it does |
| --- | --- |
| [Image downloader](#run) | Archives seven AIA views as untouched, timestamped NASA browse JPEGs |
| [Solar Horizon for macOS](#solar-horizon-for-macos) | Animated desktop and companion screensaver with Solar Horizon, Surface Scroll and Solar Peek views |
| [Plasma wallpapers](#plasma-wallpapers) | Deterministic close-up crops for landscape, portrait, square and ultrawide displays |
| [Image-quality review tools](#image-quality-review-tools) | Separate JPEG/FITS and local AI-upscaling experiments with provenance and comparison outputs |

## Run

```sh
python3 getSDO.py
```

The default destination is `~/Pictures/sdo-feed`, which is created automatically.
The original seven views are downloaded at their original 4096 x 4096 resolution: `aia_131`, `aia_171`, `aia_193`, `aia_211`, `aia_304`, `aia_335`, and `aia_1700`.
Choose that folder as the image source in your photo screensaver.

To choose a destination, fewer views, or smaller images:

```sh
python3 getSDO.py --output ./solar-images --views aia_171 aia_304 --resolution 1024
python3 getSDO.py --help
```

Paths containing spaces should be quoted.
Available resolutions are 512, 1024, 2048, and 4096 pixels.
Use `--timeout 60` to allow a longer network timeout per request.

## Solar Horizon for macOS

Solar Horizon renders a teal / pewter solar horizon with one clockwise revolution every 20 minutes at a constant 0.3 degrees per second.
The horizon stays fixed while the outer solar band moves underneath it.
It uses the actual SDO/AIA 193 Å browse-image pixels, with deterministic colour grading and a footer-safe circular mask.
The glow is restrained and has no pulsing or animated exposure.
This is an artistic rotation of a still observation, not the Sun's physical rotation.

The menu bar dropdown offers three checked view choices: **Solar Horizon**, **Surface Scroll** and **Solar Peek**.
Surface Scroll gently sweeps across the entire prepared image in a seamless 20-minute loop, easing through each turn.
It keeps one source pixel per physical display pixel, including Retina displays, without enlarging or rotating the image.
The full image is visited in horizontal passes, with a quiet return along its edge.
Displays larger than the image show black space around the native-sized image rather than stretching it.
Solar Peek keeps a fixed crop offset to the right, with a curved limb and quiet black space on the left.
The solar surface rotates clockwise at the same constant 20-minute period as Solar Horizon, while its position and native pixel scale stay fixed.
The app retains the Solar Horizon name and Corona menu bar icon.
Your view choice is saved and shared with the companion screensaver.
The small System Settings preview scales the display's composition to fit its preview area.
The menu also offers **Preview**, **Pause / resume**, **Refresh now**, **Open originals** and **Quit**.

The desktop uses Metal; the companion `.saver` draws retained images through AppKit with its own frame clock to survive macOS remote preview lifecycle changes.
Both use the same source textures, selected view geometry and continuous system clock.
The screensaver runs at 30 fps, dropping to 1 fps when paused or using Reduce Motion, and retains a visible still image after the host stops it.
New observations crossfade over 10 seconds without resetting motion.
Pause and resume preserve the current position in every view, and Reduce Motion displays a static scene.
The desktop window sits below icons, ignores mouse input and joins all Spaces.
Rendering pauses when the window is occluded or the display sleeps, with 60 fps on mains and 30 fps on battery.

The desktop build targets Apple Silicon and macOS 14 or later; the screensaver bundle includes both Apple Silicon and Intel code.
The current installation has been validated on macOS 27 with an Apple M5 and one Retina display.
Other supported OS versions and Intel screensaver hosts have not been verified.
Install with Xcode and Python 3.11 or later:

```sh
python3 scripts/install.py
```

The installer builds and locally signs the app and universal screensaver, creates a managed Python environment, and registers per-user launchd jobs.
It replaces whole bundles so loaded executables retain their original bytes, keeping prior owned versions under application support in `installation-backups` for recovery.
It installs the app in `~/Applications/Solar Horizon.app` and the companion in `~/Library/Screen Savers/Solar Horizon.saver`.
Use `--no-start` to install without starting the jobs, or `--originals PATH` to choose a separate archive.
Select **Solar Horizon** in **System Settings > Wallpaper > Screen Saver > Other > Show All** on macOS 27.
The installer does not change the system's screen-lock, password or idle-time policies.
Local signing is intended for personal installation; the bundles are not notarized for public distribution.

Refreshes are due daily at 08:00 in the Mac's local timezone.
RunAtLoad, periodic due checks and wake handling catch overdue work, without keeping Python asleep between runs.
Failures and stale NASA timestamps retry after 30 minutes, 2 hours and 6 hours, then wait for the next daily slot.
The native screensaver loads prepared scenes without the desktop app, Python or network access.
Its real macOS-host preview and lock/unlock handoff must be checked after selecting it; the deterministic renderer test does not substitute for those host checks.

| Location | Contents |
| --- | --- |
| `~/Pictures/sdo-feed` | Untouched original browse JPEGs only; all observations retained |
| `~/Library/Application Support/getSDO/scenes` | Versioned full-disc colour textures and provenance manifests |
| `~/Library/Application Support/getSDO/scene.json` | Atomic current / previous scene pointer and transition start |
| `~/Library/Application Support/getSDO/runtime` | Installed refresh scripts and managed Python environment |
| `~/Library/Caches/getSDO` | Disposable static wallpapers and previews |
| `~/Library/Logs/getSDO/refresh.log` | Refresh status, with bounded log rotation |

Original downloads are staged outside the archive, fully decoded and atomically renamed into it.
Scene metadata records the observation's UTC timestamp, scientific channel name, original SHA-256, source URL, grading version and limb geometry.
The horizon pipeline deduplicates exact observations, so a newer observation on the same UTC day can replace the active scene.
The ordinary multi-channel CLI retains its existing one-observation-per-day behaviour.
Only recognized inactive generated scenes are pruned, with the current and previous scene pinned.
Existing unrelated files and older user-created wallpaper directories are preserved.

To run a refresh manually after installing the optional image dependencies:

```sh
.venv/bin/python getSDO.py --solar-horizon --force
```

NASA's latest endpoint can be stale.
The menu and logs display the observation time and freshness status; downloading a file today does not make its observation new.
The production source remains the immutable, timestamped NASA browse JPEG.
The scientific channel is **SDO/AIA 193 Å**, equivalent to 19.3 nm extreme ultraviolet, with Fe XII and hot-flare Fe XXIV contributions documented by [NASA](https://svs.gsfc.nasa.gov/3981).
The supplied browse JPEG is already a false-colour visualization, not calibrated FITS data.

Remove the owned jobs and bundles with:

```sh
python3 scripts/uninstall.py
```

Quit Solar Horizon first if it was launched manually.
Uninstallation retains every original and the application data so reinstalling can reuse the prepared scene.

Validate with:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
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
The [implementation plan](docs/solar-horizon-implementation-plan.md) retains the original decisions and acceptance criteria.

## Plasma wallpapers

Add `--wallpaper WIDTHxHEIGHT` to automatically choose a close-up of the solar surface after each download.
For the amber "Plasma River" look, use `aia_193`:

```sh
uv run --with-requirements requirements-wallpaper.txt python getSDO.py --views aia_193 --wallpaper 3840x2160
```

Alternatively, install the optional packages into a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-wallpaper.txt
.venv/bin/python getSDO.py --views aia_193 --wallpaper 3840x2160
```

Original full-disc downloads stay in the normal output folder.
Wallpapers go into `~/Library/Caches/getSDO/wallpapers`, which you can choose as your wallpaper or screensaver source.
Derived images stay outside the originals archive.
Use `--wallpaper-output PATH` to choose a different destination.
Portrait, square and ultrawide dimensions are also supported, up to 8192 pixels per side, 40 megapixels total and a 4:1 aspect ratio.

To try an existing image without accessing NASA:

```sh
uv run --with-requirements requirements-wallpaper.txt python getSDO.py --crop "/path/to/solar-image.jpg" --wallpaper 3840x2160 --wallpaper-output ./wallpapers
```

The selector locates the solar limb in a small analysis preview and searches regions at three zoom levels and nine rotations.
It favours dark channels surrounded by bright, textured plasma, with a preference for diagonal structure.
Every crop stays inside an inset solar disc to exclude black space, the corona and the timestamp footer.
The full-resolution source supplies the final pixels; the preview is only used to choose the composition.
The output keeps the source colours, with no generated detail, recolouring or LLM/API calls.
Rotation is for composition, so wallpapers are not necessarily north-up.

The composition is selected afresh for each new source image.
Identical input pixels and aspect ratio produce the same selection, so rerunning an unchanged observation does not shuffle the wallpaper.
The selector is an aesthetic heuristic, not a scientific detector of coronal holes or solar activity.
Images without a prominent dark channel will produce a different character, and results vary across channels and observations.
Use centred, square, full-disc SDO images at least 128 pixels wide; unreadable images or an undetectable disc produce an error instead of an arbitrary crop.

Cropping reduces the available source detail.
The selected region is resized to the requested dimensions, which can involve upscaling even from a 4096-pixel original.
The command prints the native crop size and rotation so this is visible.
Requesting a 4K output does not create 4K of new detail.

Each JPEG embeds its source filename, source SHA-256, crop coordinates, rotation, output size and selector version in its EXIF `ImageDescription`.
Output names include the source stem, selector version and output dimensions.
A fully decoded wallpaper with matching source pixels, dimensions and selector version is reused on repeat runs.
Missing or damaged wallpapers are rebuilt even when the original download was skipped.
`--force` also rebuilds the wallpaper.
Writes are atomic, and a failed crop leaves both the original and any previous wallpaper intact.
The other selected views continue if one view fails.

## Image-quality review tools

These optional developer tools write comparisons under the ignored `build/` directory and leave the active scene, installed hosts, daily refresh settings and originals unchanged.
They require an existing prepared Solar Horizon scene.

To compare current JPEG sampling, cubic sampling with mild sharpening, and a matching AIA 193 Å Level 1 FITS observation:

```sh
.venv/bin/python -m pip install -r requirements-quality.txt
.venv/bin/python scripts/compare-quality.py --fits "/path/to/matching-observation.fits"
```

Open `build/quality-comparison/index.html` to inspect full frames and detail crops.
The FITS treatment reads exposure and geometry from its header and applies a display stretch; it is not a Level 1.5 scientific calibration.
The comparison has not established a meaningful sharpness gain for the cubic JPEG treatment, so it has not been applied to the daily pipeline.
`macOS/RenderIconOptions.swift` supplies the companion native menu-bar icon comparison.

To run the separate local upscaling experiment on macOS with `uv` and Xcode available:

```sh
scripts/upscale-poc.sh
```

The script creates its own Python 3.12 environment, downloads hash-verified Upscayl NCNN and Real-ESRGAN artifacts, and compares the current 4096-pixel texture with Lanczos plus mild sharpening and an 8192-pixel AI reconstruction.
It renders eight 45-degree phases, exact loop endpoints, real-speed clips and accelerated inspection clips through the production Metal shader.
It prints the comparison page location under `build/solar-horizon-upscale-poc/runs/` and records source hashes, processing settings, resource measurements and checks.
Use `--stage infer` for inference only or `--no-animation` to omit the motion clips.
Completed inference is cached and verified before reuse.
AI-generated detail is a visual reconstruction, not recovered scientific evidence, and the experiment does not enable AI upscaling in the app or screensaver.

The repository's `output/` directory contains the design concepts, colour studies and earlier crop samples.
Those concept images are visual references; production scenes use the actual NASA observation pixels and deterministic grading.

## Download behaviour

The script checks NASA's latest observation timestamp for each view and downloads the corresponding timestamped browse image over HTTPS.
This replaces the old RSS feed, which was still serving January 2020 entries when checked on 28 September 2026.
NASA documents its [image endpoints and naming conventions](https://sdo.gsfc.nasa.gov/data/bestpractice.php).

Files retain the original naming convention, for example `aia_171_20260921_152646_4096_0171.jpg`.
Dates and times are the observation's UTC timestamp, rather than the date of download.
A saved JPEG for the same observation day, view, and resolution is skipped before requesting the image again.
The timestamp is still checked on every run, so a newer observation day can be detected.
This implements the original plan to keep one image per day for each view.
It does not backfill days missed between runs.

Use `--force` to download the latest observation even when its day has already been saved.
This can add another image from that day or replace a file with the same observation timestamp.
Existing files in the original naming format are recognised.
The script never removes old images or unrelated files, including `.DS_Store`.

Downloads are checked for JPEG content type, boundary markers, size, and completeness before being moved atomically into place.
These checks catch obvious error pages and truncated downloads; they do not fully decode the JPEG.
A failed download leaves any existing image intact, reports the problem, and continues with the other views.
The exit status is 0 when all selected views are downloaded or skipped, 1 if any view fails, and 2 for invalid arguments.

An observation more than 24 hours old produces a warning, even if its image is already saved.
An old observation remains downloadable and does not by itself make the command fail.
NASA's latest timestamps were dated 21 September 2026 during the 28 September verification, so successful downloads do not imply current observations.

## Tests

Run the downloader tests without third-party packages:

```sh
python3 -m unittest discover -s tests -p test_getSDO.py -v
```

Tests use a local HTTP server and temporary directories, so they do not need internet access or write to your Pictures folder.
They exercise the real CLI, repeat runs, stale observations, invalid responses, partial failures, and safe writes.
Wallpaper tests also check selection against a known moving feature, rotation geometry, exclusion of the limb and footer, portrait and ultrawide layouts, source preservation, provenance and cache repair.
Image-dependent downloader tests are skipped when the optional packages are absent.
The complete suite also covers scene publication, daily retries, owned-bundle replacement and isolated upscale failure retention, and requires Pillow and NumPy.
Run the complete suite with:

```sh
uv run --with-requirements requirements-wallpaper.txt python -m unittest discover -s tests -v
```

For Python lint and formatting checks, install `requirements-dev.txt` into `.venv`, then run:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
xcrun swift-format lint --strict macOS/*.swift scripts/upscale-poc-render.swift
```

The Swift check and `scripts/validate-macos.sh` require macOS and Xcode.
For a live smoke test without touching your screensaver collection:

```sh
python3 getSDO.py --output /tmp/getSDO-smoke --resolution 512
```

## Suggested improvements

1. Add an optional strict freshness check and a verified fallback source, so an upstream outage cannot silently leave a daily job showing old solar activity.
2. Finish real-system battery, multi-display, sleep/wake and desktop/screensaver handoff validation, then add configurable scheduling for download-only collections alongside the installed daily AIA 193 Å scene refresh.
3. Add opt-in retention with a dry run and deletion limited to recognised getSDO files, to finish the original cleanup plan safely.
4. Add CI for supported Python versions and a separate scheduled live endpoint check, keeping network availability out of unit tests.
5. Expand the view selection to additional AIA, HMI, and composite channels after verifying their timestamp and image endpoints.

## Credits

Based on [BigPicture.py](https://gist.github.com/prehensile/675906) by Henry Cooke and originally developed as a [forked gist](https://gist.github.com/mint5auce/ec6e81b2bcb30b617c80).
Image credit: Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams.
See NASA's [media resources](https://sdo.gsfc.nasa.gov/resources/press.php).
