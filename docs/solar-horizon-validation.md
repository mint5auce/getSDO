# Solar Horizon validation

Validated on 29 September 2026 with macOS 27.0 (26A428), Apple M5, and the built-in Retina display.
The desktop application and universal legacy screensaver are installed locally with per-user launchd jobs.
System Settings has Solar Horizon selected.

## Automated checks

- All 48 Python tests pass, including download failure retention, exact-observation updates, retry bounds, corrupt-cache repair, archive separation, crop geometry, and pruning ownership.
- Ruff passes for the Python source and tests.
- Swift formatting and lint pass for the native sources.
- Optimized native builds and local code signatures validate.
- GPU captures at 0 and 1,200 seconds have identical pixels.
- Metal and AppKit screensaver geometry agree at all four quarter-turn phases, with mean RGB differences below 0.2 out of 255 and 99th-percentile differences at most 2.
- Both renderers have pixel-identical zero / 1,200-second loop endpoints.
- The desktop Metal renderer's 10-second crossfade has correct endpoints and a linear-light midpoint.
- The native test host now also initializes the screensaver with an empty frame, attaches and resizes it, and captures it without calling `startAnimation`.
- AppKit snapshots remain identical through five detach/start/stop cycles, retaining solar detail and the quiet upper sky.

## Process soak

The desktop process ran for 1,200.053 seconds with 41 observations and no process exit.
Observed CPU usage was 3.4% to 6.4%, and resident memory was approximately 181 to 193 MiB.
This soak preceded the final preview lifecycle changes.
It measures process continuity and resource usage, not GPU power, frame delivery, or visual continuity through a system lock.

## Live source and storage

NASA's latest 193 Å endpoint reported the 21 September 2026 15:38:05 UTC observation during installation.
The app correctly reports that source as stale and keeps the latest available prepared scene.
The existing seven original JPEG files in `~/Pictures/sdo-feed` are preserved.
The archive contains no generated textures, temporary staging directories, or derivative subdirectories.
Derived scenes, manifests, installed Python runtime, and logs are stored separately.

## macOS host validation

The user reproduced a black preview after selecting Solar Horizon in System Settings.
The real legacy host creates an empty preview frame and may stop animation before requesting a snapshot.
The saver now draws retained images through AppKit with a view-owned frame clock, independent of remote Metal drawables and host animation callbacks.
Repeated host captures exposed Retina geometry changes: bounds alone, or both frame and bounds, could become 2940 x 1912 while the window and drawing context stayed at 1470 x 956.
The renderer detects this exact backing-scale mismatch and uses the logical window extent for horizon geometry.
Native regression captures reproduce both variants and remain pixel-identical to the correctly sized frame.
After installing the final bundle, a fresh System Settings launch and five consecutive switches away from and back to Solar Horizon all showed the correct teal horizon and quiet upper sky.
Reopening the sheet again after those five switches also retained the correct preview.
Screenshots are saved under `build/preview-reliability/final-switch*.png`, with a comparison sheet at `final-proof.png`.
The earlier one-off preview success was insufficient evidence; these repeated checks supersede it.
The installer now stages complete bundles and preserves previous owned bundles, avoiding writes to executables still mapped by a running host.
Only host processes confirmed to have loaded Solar Horizon were refreshed.
Launching the native ScreenSaverEngine previously activated the lock screen; no further full-screen launch was attempted during these preview checks.
No password or idle policy was changed.

Battery operation, multiple displays, sleep/wake, and continuous desktop-to-screensaver-to-desktop handoff remain unverified on the real system.
Do not treat the deterministic GPU comparison as a substitute for those checks.

## Image quality and icon review

The active JPEG and matching original Level 1 FITS observation both have 4096 x 4096 source pixels.
The current horizon geometry enlarges the solar limb by approximately 1.8 times on this Retina display.
Review samples at 2940 x 1912 compare the current sampling, cubic sampling with restrained luminance sharpening, and FITS intensity data with exposure normalization and a display stretch.
The FITS sample uses header-based centre, plate scale and roll; it is a display treatment rather than a Level 1.5 scientific calibration.
Provenance and the untouched FITS source are stored separately under `build/quality-comparison`.
The generated comparison does not publish an active scene or change daily refresh behaviour.
Five available native SF Symbols are rendered at menu-bar size on light and dark backgrounds in `menu-bar-icons.png`.
The selected Corona icon (`sun.haze`) is installed as a native template SF Symbol.
Audit measurements show the cubic JPEG differs from the baseline by only 0.057 levels out of 255 on average.
The recommendation to apply that treatment is withdrawn; no meaningful sharpness gain has been established.
The files are distinct and use distinct processing, but no image pipeline change has been applied.
The subsequently requested Surface Scroll option supplies a native-pixel alternative without changing the source or grading pipeline.

## Surface Scroll

Solar Horizon 1.3 adds checked Solar Horizon and Surface Scroll choices to the menu bar dropdown.
The app name and Corona icon are retained.
Surface Scroll scans every part of the prepared texture in horizontal passes over 1,200 seconds, with smooth turns and a return along the edge.
One source pixel occupies one physical display pixel in the desktop and full-size screensaver.
Small System Settings previews scale the display's composition to fit, avoiding an isolated black source corner.

The native validation checks both renderers against unchanged source crops at four phases.
Mean RGB differences are below 0.5 out of 255, with 99th-percentile differences at most 2.
Both new-mode renderers have pixel-identical zero / 1,200-second endpoints, and Retina bounds mutation preserves the screensaver crop.
Coverage checks include 2940 x 1912, 1280 x 800, 1536 x 2048 and 5120 x 2880 viewports.
Pause/resume preserves the position, view choice and other saved settings.
All 48 Python tests, Ruff, Swift lint, native renderer checks and installed code signature checks pass.

The installed app's native menu actions were used to select Surface Scroll, pause it, switch to Solar Horizon and back, and resume it.
The preview window updates its title and composition with the selected mode.
The real System Settings screensaver preview displayed Surface Scroll after opening the Screen Saver sheet.
Both installed binary hashes match the validated build, and all seven originals retain their pre-installation hashes.
Surface Scroll remained selected and running after that validation.
A full live 20-minute Surface Scroll soak and lock/unlock handoff were not repeated.

## Solar Peek

Solar Horizon 1.4 adds Solar Peek as the third menu bar view choice.
It keeps a fixed native-resolution crop offset to the right, with the left limb matching the user's supplied reference.
The surface rotates clockwise once every 1,200 seconds at a constant angular speed, sharing the existing clock, pause state and screensaver selection.
The source image, colour grade and glow are unchanged.

The reference matches a native crop of the active 4096-pixel texture.
Its solar centre is approximately (2040, 1160) within the 1984 x 1294 reference, and its source limb radius is 1632 pixels.
The placement follows the limb near 45% of the top edge and 21% of the bottom edge while keeping the source radius unchanged.
Larger displays retain the native pixel scale and keep the disc toward the right.

Native captures at four quarter-turn phases agree with independently calculated unit-scale source rotations and with the packaged screensaver.
Mean RGB differences are below 0.5 out of 255, with 99th-percentile differences at most 2.
Both renderers have pixel-identical zero / 1,200-second endpoints, and Retina bounds changes preserve the crop.
The small screensaver preview remains visible at every tested phase and through three detach/start/stop cycles.
AppKit rounds a few isolated colour values by one level after reattachment; the restart check permits only that measured rounding.
Validation captures explicitly select their mode and phase so the user's saved pause and phase offset cannot affect the checks.
All 48 Python tests, Ruff, Swift lint, native image comparisons and local signing checks pass.

The installed native menu was used to select Solar Peek, open its preview, pause it and resume it.
System Settings initially retained two hosts mapped to the prior screensaver bundle, so those confirmed Solar Horizon hosts were stopped after closing the preview sheet.
Reopening the sheet loaded the current bundle and displayed the correct Solar Peek composition.
System Settings was restored to its previous Login Items page, and Solar Peek remains selected and running.
The seven original files retain their pre-installation hashes.
A full live 20-minute Solar Peek soak and lock/unlock handoff were not repeated.
