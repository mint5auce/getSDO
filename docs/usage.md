# Usage

Requires Python 3.11 or newer.
Download-only mode uses the Python standard library; plasma crops require Pillow and NumPy.
Run commands from the repository root.

## Download images

```sh
python3 solar_horizon.py
```

The default destination is `~/Pictures/sdo-feed`, which is created automatically.
The original seven views are downloaded at their original 4096 x 4096 resolution: `aia_131`, `aia_171`, `aia_193`, `aia_211`, `aia_304`, `aia_335`, and `aia_1700`.
Choose that folder as the image source in your photo screensaver.

To choose a destination, fewer views, or smaller images:

```sh
python3 solar_horizon.py --output ./solar-images --views aia_171 aia_304 --resolution 1024
python3 solar_horizon.py --help
```

Paths containing spaces should be quoted.
Available resolutions are 512, 1024, 2048, and 4096 pixels.
Use `--timeout 60` to allow a longer network timeout per request.

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

## Plasma wallpapers

Add `--wallpaper WIDTHxHEIGHT` to automatically choose a close-up of the solar surface after each download.
For the amber "Plasma River" look, use `aia_193`:

```sh
uv run --with-requirements requirements-wallpaper.txt python solar_horizon.py --views aia_193 --wallpaper 3840x2160
```

Alternatively, install the optional packages into a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-wallpaper.txt
.venv/bin/python solar_horizon.py --views aia_193 --wallpaper 3840x2160
```

Original full-disc downloads stay in the normal output folder.
Wallpapers go into `~/Library/Caches/Solar Horizon/wallpapers`, which you can choose as your wallpaper or screensaver source.
Derived images stay outside the originals archive.
Use `--wallpaper-output PATH` to choose a different destination.
Portrait, square and ultrawide dimensions are also supported, up to 8192 pixels per side, 40 megapixels total and a 4:1 aspect ratio.

To try an existing image without accessing NASA:

```sh
uv run --with-requirements requirements-wallpaper.txt python solar_horizon.py --crop "/path/to/solar-image.jpg" --wallpaper 3840x2160 --wallpaper-output ./wallpapers
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
