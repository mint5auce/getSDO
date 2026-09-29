#!/bin/sh
# Dependencies belong exclusively to this review workspace.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
poc="$repo/build/solar-horizon-upscale-poc"
mkdir -p "$poc"
export UV_CACHE_DIR="$poc/uv-cache"
if [ ! -x "$poc/runtime/bin/python" ]; then
  uv venv --python 3.12 "$poc/runtime"
fi
uv pip install --python "$poc/runtime/bin/python" -r "$repo/scripts/upscale-poc-requirements.txt"
exec "$poc/runtime/bin/python" "$repo/scripts/upscale-poc.py" "$@"
