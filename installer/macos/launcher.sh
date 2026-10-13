#!/bin/sh
# Main executable of "mpv AnimeJaNai.app". mpv does not read settings from its bundle, so the
# application keeps a data folder laid out like the Linux one:
#   ~/Library/Application Support/AnimeJaNai/portable_config   mpv settings (MPV_HOME)
#   ~/Library/Application Support/AnimeJaNai/animejanai        profiles (animejanai.conf)
# Scripts, HDR tools and shaders are refreshed from the application at every launch; settings
# files are only created when missing, so that edits are kept.
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"
DATA="$HOME/Library/Application Support/AnimeJaNai"
CONF="$DATA/portable_config"
SRC="$RES/animejanai-config"
mkdir -p "$CONF/script-opts" "$DATA/animejanai" "$HOME/Library/Caches/AnimeJaNai"
for managed in scripts hdr-tools user-shaders; do
    rm -rf "$CONF/$managed"
    cp -R "$SRC/$managed" "$CONF/$managed"
done
for file in mpv.conf script-opts/animejanai_mac.conf script-opts/animejanai_hdr_auto.conf; do
    [ -f "$CONF/$file" ] || cp "$SRC/$file" "$CONF/$file"
done
[ -f "$DATA/animejanai/animejanai.conf" ] || cp "$RES/animejanai/animejanai.conf" "$DATA/animejanai/animejanai.conf"
# Models: a folder of the user's, filled with links to the application's models. The Manager
# lists it and the engine reads it; a model the user adds there stays through updates. Links to
# models an update removed are dropped.
MODELS="$DATA/animejanai/onnx"
mkdir -p "$MODELS"
for link in "$MODELS"/*; do
    if [ -L "$link" ] && [ ! -e "$link" ]; then rm -f "$link"; fi
done
for model in "$RES/animejanai/onnx"/*; do
    [ -e "$model" ] || continue
    target="$MODELS/$(basename "$model")"
    if [ -L "$target" ] || [ ! -e "$target" ]; then ln -sfn "$model" "$target"; fi
done
# "Run Benchmarks" of the Manager looks for its launcher in the data folder.
if [ -d "$RES/animejanai/benchmarks" ] && { [ -L "$DATA/animejanai/benchmarks" ] || [ ! -e "$DATA/animejanai/benchmarks" ]; }; then
    ln -sfn "$RES/animejanai/benchmarks" "$DATA/animejanai/benchmarks"
fi
# Once per Mac: with an XDR display (MacBook Pro, Pro Display XDR), SDR video is converted to HDR
# and the display is described (1600 nits peak, not OLED), as the other platforms do when HDR
# output is available. Only settings still at their shipped value are changed; afterwards the
# file is the user's. Ctrl+h in the player turns the conversion off and on.
hdr="$CONF/script-opts/animejanai_hdr_auto.conf"
if [ ! -f "$DATA/.display-defaults" ] && [ -f "$hdr" ]; then
    kind=other
    if "${ANIMEJANAI_DISPLAY_PROBE:-system_profiler}" SPDisplaysDataType 2>/dev/null | grep -q 'XDR'; then
        kind=xdr
        if grep -q '^linux_hdr_output=auto' "$hdr" && grep -q '^display_peak=auto' "$hdr"; then
            sed -e 's/^linux_hdr_output=auto/linux_hdr_output=pq/' -e 's/^display_peak=auto/display_peak=1600/' \
                "$hdr" > "$hdr.new" && mv "$hdr.new" "$hdr"
            kind=xdr-hdr
        fi
    fi
    echo "$kind" > "$DATA/.display-defaults"
fi
export MPV_HOME="$CONF"
export ANIMEJANAI_BUNDLE="$RES"
export ANIMEJANAI_ROOT="$DATA"
export ANIMEJANAI_DATA_DIR="$DATA/animejanai"
# Compiled models: out of the application (read-only once installed) and kept through updates.
export AJI_ORT_CACHE="$HOME/Library/Caches/AnimeJaNai/coreml"
# A socket of this player only: the Manager (Ctrl+E) tells it to apply what was saved. The
# launcher is replaced by the player, so the socket is named after the process that owns it;
# sockets left by earlier players are removed.
SOCKETS="${TMPDIR:-/tmp}"
find "$SOCKETS" -maxdepth 1 -name 'animejanai-mpv-*.sock' -mtime +1 -delete 2>/dev/null
export ANIMEJANAI_IPC_PATH="${SOCKETS%/}/animejanai-mpv-$$.sock"
exec "$HERE/mpv" --input-ipc-server="$ANIMEJANAI_IPC_PATH" "$@"
