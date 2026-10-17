#!/bin/bash
# Builds the pinned mpv with the AnimeJaNai host-frame filter on macOS (Apple Silicon) and makes
# mpv.app with its libraries bundled. Dependencies come from Homebrew.
# Usage: build-mpv.sh WORK OUTPUT
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${1:?usage: build-mpv.sh WORK OUTPUT}"
OUTPUT="${2:?output directory required}"
MPV_REVISION=19c0fcf89595e6ab33908299207c555b67e81558
mkdir -p "$WORK" "$OUTPUT"
WORK="$(cd "$WORK" && pwd)"; OUTPUT="$(cd "$OUTPUT" && pwd)"

if [ ! -d "$WORK/mpv/.git" ]; then git clone --filter=blob:none https://github.com/the-database/mpv.git "$WORK/mpv"; fi
git -C "$WORK/mpv" checkout --detach "$MPV_REVISION"
python3 "$REPO/native/linux-vulkan/install-filter.py" "$WORK/mpv"

cd "$WORK/mpv"
meson setup build --buildtype=release -Dlibmpv=false -Dvulkan=enabled -Dlua=enabled \
    -Dcuda-hwaccel=disabled -Dcuda-interop=disabled -Dmanpage-build=disabled
meson compile -C build
build/mpv --no-config --vf=help | grep animejanai-vulkan
build/mpv --no-config --gpu-context=help | tee "$OUTPUT/gpu-contexts.txt"

# mpv.app with every non-system library copied inside.
python3 TOOLS/osxbundle.py build/mpv
rm -rf "$OUTPUT/mpv.app"
cp -R build/mpv.app "$OUTPUT/mpv.app"
"$OUTPUT/mpv.app/Contents/MacOS/mpv" --no-config --version | head -3
otool -L "$OUTPUT/mpv.app/Contents/MacOS/mpv" | grep -c -E '/opt/homebrew|/usr/local' || true
printf 'mpv=%s\nvulkan_bridge_abi=1\n' "$MPV_REVISION" > "$OUTPUT/build-info.txt"
