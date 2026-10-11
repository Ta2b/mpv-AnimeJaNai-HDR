#!/usr/bin/env bash
# Runs the HDR controller tests against a scratch copy of the overlay's portable_config.
# usage: tests/hdr/run.sh [lua interpreter...]   (default: luajit, plus lua5.2 when installed)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
overlay="$here/../../BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config"
interps=("$@")
if [ ${#interps[@]} -eq 0 ]; then
  for i in luajit lua5.2; do command -v "$i" >/dev/null && interps+=("$i"); done
fi
[ ${#interps[@]} -gt 0 ] || { echo "no Lua interpreter found" >&2; exit 2; }
status=0
for lua in "${interps[@]}"; do
  for t in run_tests run_slot_tests run_startup_tests run_rife_tests run_vulkan_tests; do
    scratch="$(mktemp -d)"
    mkdir -p "$scratch/portable_config/cache" "$scratch/animejanai"
    cp -r "$overlay"/{hdr-tools,user-scripts,user-shaders,script-opts,profiles} "$scratch/portable_config/"
    printf '%-8s %-18s ' "$lua" "$t"
    if AJ_ROOT="$scratch/portable_config" AJ_TEST_DIR="$here" "$lua" "$here/$t.lua"; then :; else status=1; fi
    rm -rf "$scratch"
  done
done
exit $status
