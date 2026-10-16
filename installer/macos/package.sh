#!/bin/bash
# Assembles "mpv AnimeJaNai.app" for macOS (Apple Silicon): mpv.app, the settings and scripts, the
# models, the engine (Core ML through ONNX Runtime, Core ML alone, Metal), the Manager and the
# updater.
# Usage: package.sh MPV_APP ENGINE_DIR ONNX_DIR VERSION OUTPUT_DIR [MANAGER_APP [UPDATER [PLATFORM]]]
#   ENGINE_DIR:  libaji_ort.dylib, libonnxruntime*.dylib, the engine test program, the benchmark
#                files and onnx/ (what the engine build prepared from the models)
#   MANAGER_APP: "AnimeJaNai Manager.app" of the Manager build, opened by Ctrl+E
#   UPDATER:     AnimeJaNaiUpdater published for osx-arm64 (Ctrl+U replaces the application
#                with the one of the latest release)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MPV_APP="${1:?mpv.app}"; ENGINE="${2:?engine directory}"; ONNX="${3:?onnx directory}"
VERSION="${4:?version}"; OUT="${5:?output directory}"; MANAGER="${6:-}"; UPDATER="${7:-}"
PLATFORM="${8:-}"
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
if [ -n "$PLATFORM" ]; then
    install -m755 "$PLATFORM" "$RES/AnimeJaNaiPlatform"
    cp "$PC/scripts/animejanai_reference.lua" "$CONF/scripts/"
fi
mkdir -p "$CONF/hdr-tools" "$CONF/user-shaders"
cp "$PC/hdr-tools/gpu-policy.lua" "$PC/hdr-tools/hdr-grade.lua" "$PC/hdr-tools/linux-hdr.lua" "$CONF/hdr-tools/"
cp "$PC/hdr-tools/playback-state.lua" "$CONF/hdr-tools/"
cp "$PC/scripts/animejanai_playback.lua" "$CONF/scripts/"
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
# The RIFE models chosen for macOS, their picture size named so that Core ML takes them
# (native/linux-ort/name_rife_dims.py).
if [ -d "$ENGINE/rife" ]; then
    mkdir -p "$RES/animejanai/rife"
    cp "$ENGINE/rife/"*.onnx "$RES/animejanai/rife/"
fi
cp "$ENGINE/libaji_ort.dylib" "$RES/animejanai/inference/"
# One ONNX Runtime file, under the name the engine links to.
cp -L "$ENGINE/libonnxruntime.1.dylib" "$RES/animejanai/inference/libonnxruntime.1.dylib"
install_name_tool -add_rpath @loader_path "$RES/animejanai/inference/libaji_ort.dylib" 2>/dev/null || true
# The engine comparison behind the Manager's "Run Benchmarks": the test program next to the
# engine it loads, the scripts in animejanai/benchmarks.
if [ -f "$ENGINE/animejanai-ort-test" ]; then
    mkdir -p "$RES/animejanai/benchmarks"
    install -m755 "$ENGINE/animejanai-ort-test" "$RES/animejanai/inference/animejanai-ort-test"
    install_name_tool -add_rpath @loader_path "$RES/animejanai/inference/animejanai-ort-test" 2>/dev/null || true
    install -m755 "$ENGINE/bench.command" "$RES/animejanai/benchmarks/bench.command"
    cp "$ENGINE/bench.conf" "$RES/animejanai/benchmarks/bench.conf"
    install -m755 "$HERE/animejanai_benchmark_all.sh" "$RES/animejanai/benchmarks/animejanai_benchmark_all.sh"
fi
if [ -n "$MANAGER" ]; then
    [ -x "$MANAGER/Contents/MacOS/AnimeJaNaiManager-HDR" ] || { echo "Manager application incomplete: $MANAGER" >&2; exit 1; }
    cp -R "$MANAGER" "$RES/AnimeJaNai Manager.app"
fi
# The updater and the script that drives it (shared with the other platforms). manifest.json is
# what the updater reads on every platform: here, an application replaced as a whole.
if [ -n "$UPDATER" ]; then
    install -m755 "$UPDATER" "$RES/AnimeJaNaiUpdater"
    cp "$PC/scripts/animejanai_update.lua" "$CONF/scripts/"
fi
printf '%s\n' "$VERSION" > "$RES/animejanai/version.txt"
printf '%s\n' "$VERSION" > "$RES/version.txt"
cat > "$RES/manifest.json" <<EOF
{
  "version": "$VERSION",
  "platform": "osx-arm64",
  "install": "application",
  "player_executable": "mpv",
  "player_launcher": "mpv-animejanai",
  "update_asset_suffix": "-macos-arm64.zip"
}
EOF

plist="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable mpv-animejanai" "$plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'mpv AnimeJaNai'" "$plist" || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier io.github.ta2b.mpv-animejanai" "$plist" || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$plist" || true

# Ad-hoc signature: required on Apple Silicon. The application is not notarized.
# What is in Resources is sealed as data by the application's signature, not signed as code:
# every program and library there gets its own signature first, the Manager as an application.
find "$RES" -type f -not -path '*/AnimeJaNai Manager.app/*' | while IFS= read -r f; do
    if file -b "$f" | grep -q 'Mach-O'; then codesign --force -s - "$f"; fi
done
if [ -d "$RES/AnimeJaNai Manager.app" ]; then
    codesign --force --deep -s - "$RES/AnimeJaNai Manager.app"
    codesign --verify --deep "$RES/AnimeJaNai Manager.app"
fi
codesign --force --deep -s - "$APP"
codesign --verify --deep "$APP"
echo "$APP"
