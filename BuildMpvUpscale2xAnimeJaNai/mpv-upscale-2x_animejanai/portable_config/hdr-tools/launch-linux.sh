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
# TrueHDR stage (libaji_rtx.so): NVIDIA Maxine Video Effects loads its own CUDA, TensorRT and
# feature libraries by name. They go last, after the player's own libraries.
vfx="${ANIMEJANAI_VFX_SDK:-/usr/local/VideoFX}"
if [ -f "$ANIMEJANAI_INFERENCE_DIR/libaji_rtx.so" ] && [ -d "$vfx/lib" ]; then
    for dir in "$vfx/lib" "$vfx"/features/*/lib "$vfx/external/cuda/lib" "$vfx/external/tensorrt/lib"; do
        if [ -d "$dir" ]; then LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$dir"; fi
    done
    export LD_LIBRARY_PATH
fi
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
