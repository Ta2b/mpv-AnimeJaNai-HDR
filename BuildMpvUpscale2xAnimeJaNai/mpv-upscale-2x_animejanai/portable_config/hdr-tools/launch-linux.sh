#!/bin/sh
# Portable Linux launcher. AppRun supplies alternate immutable binary/writable data roots.
set -eu
umask 077
HERE="$(dirname "$(readlink -f "$0")")"
ANIMEJANAI_ROOT="${ANIMEJANAI_ROOT:-$HERE}"
ANIMEJANAI_MPV="${ANIMEJANAI_MPV:-$HERE/mpv/mpv}"
ANIMEJANAI_INFERENCE_DIR="${ANIMEJANAI_INFERENCE_DIR:-$HERE/animejanai/inference}"
export ANIMEJANAI_ROOT ANIMEJANAI_MPV ANIMEJANAI_INFERENCE_DIR
export ANIMEJANAI_DATA_DIR="$ANIMEJANAI_ROOT/animejanai"
export LD_LIBRARY_PATH="$HERE/mpv:$ANIMEJANAI_INFERENCE_DIR:${ANIMEJANAI_EXTRA_LIBS:-}:${LD_LIBRARY_PATH:-}"
# TrueHDR (ordered pipeline or legacy libaji_rtx.so): NVIDIA Maxine Video Effects loads its own CUDA, TensorRT and
# feature libraries by name. They go last, after the player's own libraries.
vfx="${ANIMEJANAI_VFX_SDK:-/usr/local/VideoFX}"
if { [ -f "$ANIMEJANAI_INFERENCE_DIR/libaji_rtx.so" ] || [ -f "$ANIMEJANAI_INFERENCE_DIR/libaji_pipeline.so" ]; } && [ -d "$vfx/lib" ]; then
    for dir in "$vfx/lib" "$vfx"/features/*/lib "$vfx/external/cuda/lib" "$vfx/external/tensorrt/lib"; do
        if [ -d "$dir" ]; then LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$dir"; fi
    done
    export LD_LIBRARY_PATH
fi
# NVIDIA Smooth Motion: the driver's Vulkan layer reads this variable when the player starts.
# A value already set in the environment wins over the setting.
hdr_conf="$ANIMEJANAI_ROOT/portable_config/script-opts/animejanai_hdr_auto.conf"
if [ -z "${NVPRESENT_ENABLE_SMOOTH_MOTION:-}" ] && [ -f "$hdr_conf" ] &&
    grep -qiE '^[[:space:]]*smooth_motion[[:space:]]*=[[:space:]]*(yes|true|1)[[:space:]]*(#.*)?$' "$hdr_conf"; then
    export NVPRESENT_ENABLE_SMOOTH_MOTION=1
fi
# Started without a file (menu entry, double click): open the player window and wait for a
# file to be dropped or opened, instead of exiting at once as the command-line player does.
[ "$#" -gt 0 ] || set -- --player-operation-mode=pseudo-gui
runtime="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
session="$(mktemp -d "$runtime/animejanai-hdr.XXXXXXXX")"
export ANIMEJANAI_IPC_PATH="$session/mpv.sock"
cleanup() { rm -f "$ANIMEJANAI_IPC_PATH"; rmdir "$session" 2>/dev/null || true; }
trap cleanup EXIT
stop() { kill -TERM "${player_pid:-}" 2>/dev/null || true; wait "${player_pid:-}" 2>/dev/null || true; exit 143; }
trap stop TERM INT HUP
"$ANIMEJANAI_MPV" --config-dir="$ANIMEJANAI_ROOT/portable_config" --input-ipc-server="$ANIMEJANAI_IPC_PATH" "$@" &
player_pid=$!
status=0
wait "$player_pid" || status=$?
exit "$status"
