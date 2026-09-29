# Image-quality review tools

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
