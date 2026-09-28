# getSDO

Download the latest available solar images from NASA's Solar Dynamics Observatory for a photo screensaver or local collection.
Requires Python 3.11 or newer and an internet connection, with no third-party Python dependencies.

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

```sh
python3 -m unittest discover -s tests -v
```

Tests use a local HTTP server and temporary directories, so they do not need internet access or write to your Pictures folder.
They exercise the real CLI, repeat runs, stale observations, invalid responses, partial failures, and safe writes.
For a live smoke test without touching your screensaver collection:

```sh
python3 getSDO.py --output /tmp/getSDO-smoke --resolution 512
```

## Suggested improvements

1. Add an optional strict freshness check and a verified fallback source, so an upstream outage cannot silently leave a daily job showing old solar activity.
2. Provide a configurable macOS `launchd` job for unattended daily downloads, with logs and an absolute Python path.
3. Add opt-in retention with a dry run and deletion limited to recognised getSDO files, to finish the original cleanup plan safely.
4. Add CI for supported Python versions and a separate scheduled live endpoint check, keeping network availability out of unit tests.
5. Expand the view selection to additional AIA, HMI, and composite channels after verifying their timestamp and image endpoints.

## Credits

Based on [BigPicture.py](https://gist.github.com/prehensile/675906) by Henry Cooke and originally developed as a [forked gist](https://gist.github.com/mint5auce/ec6e81b2bcb30b617c80).
Image credit: Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams.
See NASA's [media resources](https://sdo.gsfc.nasa.gov/resources/press.php).
