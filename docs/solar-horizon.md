# Solar Horizon for macOS

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

## Installation

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

## Refresh and storage

Refreshes are due daily at 08:00 in the Mac's local timezone.
RunAtLoad, periodic due checks and wake handling catch overdue work, without keeping Python asleep between runs.
Failures and stale NASA timestamps retry after 30 minutes, 2 hours and 6 hours, then wait for the next daily slot.
The native screensaver loads prepared scenes without the desktop app, Python or network access.
Its real macOS-host preview and lock/unlock handoff must be checked after selecting it; the deterministic renderer test does not substitute for those host checks.

| Location | Contents |
| --- | --- |
| `~/Pictures/sdo-feed` | Untouched original browse JPEGs only; all observations retained |
| `~/Library/Application Support/Solar Horizon/scenes` | Versioned full-disc colour textures and provenance manifests |
| `~/Library/Application Support/Solar Horizon/scene.json` | Atomic current / previous scene pointer and transition start |
| `~/Library/Application Support/Solar Horizon/runtime` | Installed refresh scripts and managed Python environment |
| `~/Library/Caches/Solar Horizon` | Disposable static wallpapers and previews |
| `~/Library/Logs/Solar Horizon/refresh.log` | Refresh status, with bounded log rotation |

Upgrades reuse an existing `~/Library/Application Support/getSDO` directory when the new support directory is absent, preserving saved scenes and their absolute paths.
The installer replaces owned bundles and retires the old launch jobs; original downloads stay in `~/Pictures/sdo-feed`.

Original downloads are staged outside the archive, fully decoded and atomically renamed into it.
Scene metadata records the observation's UTC timestamp, scientific channel name, original SHA-256, source URL, grading version and limb geometry.
The horizon pipeline deduplicates exact observations, so a newer observation on the same UTC day can replace the active scene.
The ordinary multi-channel CLI retains its existing one-observation-per-day behaviour.
Only recognized inactive generated scenes are pruned, with the current and previous scene pinned.
Existing unrelated files and older user-created wallpaper directories are preserved.

To run a refresh manually after installing the optional image dependencies:

```sh
.venv/bin/python solar_horizon.py --solar-horizon --force
```

NASA's latest endpoint can be stale.
The menu and logs display the observation time and freshness status; downloading a file today does not make its observation new.
The production source remains the immutable, timestamped NASA browse JPEG.
The scientific channel is **SDO/AIA 193 Å**, equivalent to 19.3 nm extreme ultraviolet, with Fe XII and hot-flare Fe XXIV contributions documented by [NASA](https://svs.gsfc.nasa.gov/3981).
The supplied browse JPEG is already a false-colour visualization, not calibrated FITS data.

## Uninstallation

Remove the owned jobs and bundles with:

```sh
python3 scripts/uninstall.py
```

Quit Solar Horizon first if it was launched manually.
Uninstallation retains every original and the application data so reinstalling can reuse the prepared scene.

See [development checks](../CONTRIBUTING.md#native-validation) and the [validation record](solar-horizon-validation.md) for verification details.
