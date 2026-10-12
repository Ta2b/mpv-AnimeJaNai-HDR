#!/bin/bash
# Builds the AnimeJaNai AppImage from an assembled linux-x64 tree, including an
# SDR-only test tree. Optional components install into the writable data root
# $XDG_DATA_HOME/AnimeJaNai-HDR-linux through AppRun and the Manager.
#
# Usage: build-appimage.sh <tree-dir> <version> [out-dir]
#
# linuxdeploy gathers mpv's shared-lib deps; the AppImage excludelist keeps the
# host-provided graphics stack out (libvulkan, libGL, libwayland, glibc, …).
# Runs headless via APPIMAGE_EXTRACT_AND_RUN (no FUSE needed on CI runners).
set -euo pipefail

TREE="$1"
VER="$2"
OUT="${3:-.}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
APPDIR="$WORK/AppDir"
export APPIMAGE_EXTRACT_AND_RUN=1
export ARCH=x86_64

[ -d "$TREE" ] || { echo "tree not found: $TREE" >&2; exit 1; }

# --- tools (download the single-file AppImage tools if not on PATH) --------
tooldir="$WORK/tools"; mkdir -p "$tooldir"
fetch() { # url dest
    if ! command -v "$(basename "$2")" >/dev/null 2>&1; then
        curl -fsSL "$1" -o "$2/$(basename "$1")"; chmod +x "$2/$(basename "$1")"
        echo "$2/$(basename "$1")"
    else command -v "$(basename "$2")"; fi
}
LD=$(fetch "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage" "$tooldir")
AT=$(fetch "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" "$tooldir")

# --- assemble AppDir -------------------------------------------------------
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/bin"
cp -a "$TREE/." "$APPDIR/"
install -m755 "$HERE/AppRun" "$APPDIR/AppRun"

# icon: one from the tree if present, else the committed installer/linux/animejanai.png
# (256x256). linuxdeploy rejects an invalid or oddly sized PNG, so nothing is generated here.
icon="$APPDIR/mpv-animejanai.png"
if   [ -f "$TREE/portable_config/animejanai.png" ]; then cp "$TREE/portable_config/animejanai.png" "$icon"
elif [ -f "$HERE/animejanai.png" ]; then cp "$HERE/animejanai.png" "$icon"
else
    echo "icon not found: $HERE/animejanai.png" >&2; exit 1
fi

cat > "$APPDIR/mpv-animejanai.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=mpv AnimeJaNai
GenericName=Media Player
Comment=Real-time anime upscaling video player (mpv + TensorRT)
Exec=AppRun %U
Icon=mpv-animejanai
Terminal=false
Categories=AudioVideo;Player;Video;
MimeType=video/x-matroska;video/mp4;video/webm;video/x-msvideo;video/quicktime;video/mpeg;
EOF

# --- bundle mpv's deps (excludelist keeps host graphics libs out) ----------
# Point linuxdeploy at the real mpv binary; it walks NEEDED and copies the
# non-excluded libs into usr/lib. The bundled libmpv/libplacebo/ffmpeg already
# sit in mpv/ (on AppRun's LD_LIBRARY_PATH), so this mainly captures the smaller
# system deps (libass, freetype, fribidi, harfbuzz, lcms2, …).
LD_LIBRARY_PATH="$APPDIR/mpv:${LD_LIBRARY_PATH:-}" "$LD" --appdir "$APPDIR" \
    --executable "$APPDIR/mpv/mpv" \
    --library "$APPDIR/mpv/libmpv.so.2" \
    --exclude-library='libwayland*' --exclude-library='libxkbcommon*' \
    --exclude-library='libexpat*' --exclude-library='libffi*' \
    --exclude-library='libX11*' --exclude-library='libxcb*' \
    --desktop-file "$APPDIR/mpv-animejanai.desktop" \
    --icon-file "$icon"

# linuxdeploy may install its own AppRun; restore ours (we need the
# write-redirection logic, not a plain exec wrapper).
install -m755 "$HERE/AppRun" "$APPDIR/AppRun"

# --- package ---------------------------------------------------------------
mkdir -p "$OUT"
outfile="$OUT/mpv-AnimeJaNai-HDR-v${VER}-linux-x64.AppImage"
"$AT" "$APPDIR" "$outfile"
echo "$outfile"
rm -rf "$WORK"
