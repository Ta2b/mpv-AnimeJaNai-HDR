#!/bin/bash
# Assembles "mpv AnimeJaNai.app" for macOS (Apple Silicon): mpv.app, the settings and script, the
# models, and the ONNX Runtime engine with Core ML.
# Usage: package.sh MPV_APP ENGINE_DIR ONNX_DIR VERSION OUTPUT_DIR
#   ENGINE_DIR: libaji_ort.dylib and libonnxruntime*.dylib
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MPV_APP="${1:?mpv.app}"; ENGINE="${2:?engine directory}"; ONNX="${3:?onnx directory}"
VERSION="${4:?version}"; OUT="${5:?output directory}"
mkdir -p "$OUT"
APP="$OUT/mpv AnimeJaNai.app"
rm -rf "$APP"
cp -R "$MPV_APP" "$APP"
RES="$APP/Contents/Resources"

# The launcher copies these settings to the user's folder and starts mpv with MPV_HOME.
CONF="$RES/animejanai-config"
mkdir -p "$CONF/scripts" "$CONF/script-opts" "$RES/animejanai/inference" "$RES/animejanai/onnx"
cp "$HERE/config/mpv.conf" "$CONF/mpv.conf"
cp "$HERE/config/scripts/"*.lua "$CONF/scripts/"
# SDR -> HDR conversion: the HDR scripts and the shaders of the other platforms.
PC="$HERE/../../BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config"
mkdir -p "$CONF/hdr-tools" "$CONF/user-shaders"
cp "$PC/hdr-tools/gpu-policy.lua" "$PC/hdr-tools/hdr-grade.lua" "$PC/hdr-tools/linux-hdr.lua" "$CONF/hdr-tools/"
cp "$PC/user-shaders/"*.hook "$CONF/user-shaders/"
cp "$PC/script-opts/animejanai_hdr_auto.conf" "$CONF/script-opts/animejanai_hdr_auto.conf"
cp "$HERE/config/script-opts/animejanai_mac.conf" "$CONF/script-opts/"
install -m755 "$HERE/launcher.sh" "$APP/Contents/MacOS/mpv-animejanai"
cp "$HERE/config/animejanai.conf" "$RES/animejanai/animejanai.conf"
cp "$ONNX"/*SPANF3*.onnx "$RES/animejanai/onnx/"
# What the engine build prepared from those models: the ONNX variants of the ONNX Runtime engine
# (fuse_unshuffle.py), the Core ML templates with their size tables and the Metal model files
# (native/apple/convert_models.py).
if [ -d "$ENGINE/onnx" ]; then cp -R "$ENGINE/onnx/." "$RES/animejanai/onnx/"; fi
cp "$ENGINE/libaji_ort.dylib" "$RES/animejanai/inference/"
# One ONNX Runtime file, under the name the engine links to.
cp -L "$ENGINE/libonnxruntime.1.dylib" "$RES/animejanai/inference/libonnxruntime.1.dylib"
install_name_tool -add_rpath @loader_path "$RES/animejanai/inference/libaji_ort.dylib" 2>/dev/null || true
printf '%s\n' "$VERSION" > "$RES/animejanai/version.txt"

plist="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable mpv-animejanai" "$plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'mpv AnimeJaNai'" "$plist" || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier io.github.ta2b.mpv-animejanai" "$plist" || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$plist" || true

# Ad-hoc signature: required on Apple Silicon. The application is not notarized.
codesign --force --deep -s - "$APP"
codesign --verify --deep "$APP"
echo "$APP"
