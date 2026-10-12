#!/usr/bin/env bash
# Creates an isolated Linux test tarball, including the HDR Manager and updater.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${AJ_LINUX_OUTPUT:-$REPO/artifacts/linux-test}"
MANAGER="${AJ_MANAGER_SOURCE:-$REPO/../AnimeJaNaiManager-HDR}"
DOTNET="${AJ_DOTNET:-dotnet}"
VERSION="${1:-$(cat "$REPO/release-version.txt")-linux-test.1}"
: "${MPV_LINUX_LOCAL:?Set MPV_LINUX_LOCAL to a Wayland-enabled flat mpv bundle (installer/linux/build-native.sh).}"
mkdir -p "$OUTPUT/manager-hdr"
"$DOTNET" publish "$MANAGER/AnimeJaNaiConfEditor/AnimeJaNaiConfEditor.csproj" --disable-build-servers -c Release -r linux-x64 \
    --self-contained true -p:PlatformSource="$REPO/AnimeJaNaiPlatform/PlatformServices.cs" -o "$OUTPUT/manager-publish"
cp "$OUTPUT/manager-publish/AnimeJaNaiManager" "$OUTPUT/manager-hdr/AnimeJaNaiManager-HDR"
cp "$OUTPUT/manager-publish/"*.so "$OUTPUT/manager-hdr/"
"$DOTNET" publish "$REPO/AnimeJaNaiPlatform/AnimeJaNaiPlatform.csproj" --disable-build-servers -c Release -r linux-x64 \
    --self-contained true -p:PublishSingleFile=true -o "$OUTPUT/platform-linux-x64"
"$DOTNET" publish "$REPO/AnimeJaNaiUpdater/AnimeJaNaiUpdater.csproj" --disable-build-servers -c Release -r linux-x64 \
    --self-contained true -o "$OUTPUT/updater"
"$DOTNET" publish "$REPO/BuildMpvUpscale2xAnimeJaNai/BuildMpvUpscale2xAnimeJaNai.csproj" --disable-build-servers \
    -c Release -o "$OUTPUT/assembler"
export MANAGER_HDR_LOCAL="$OUTPUT/manager-hdr" PLATFORM_LOCAL="$OUTPUT/platform-linux-x64"
if [ -n "${VULKAN_LOCAL:-}" ]; then mode=--vulkan-only; else mode=--sdr-only; fi
"$DOTNET" "$OUTPUT/assembler/BuildMpvUpscale2xAnimeJaNai.dll" "$VERSION" --target linux-x64 "$mode"
"$REPO/installer/linux/package-tarball.sh" "$OUTPUT/assembler/mpv-upscale-2x_animejanai-v$VERSION" \
    "$OUTPUT/updater/AnimeJaNaiUpdater" "$VERSION" "$OUTPUT"
