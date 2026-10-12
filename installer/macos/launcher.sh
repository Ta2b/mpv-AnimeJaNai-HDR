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
export MPV_HOME="$CONF"
export ANIMEJANAI_BUNDLE="$RES"
export ANIMEJANAI_ROOT="$DATA"
export ANIMEJANAI_DATA_DIR="$DATA/animejanai"
exec "$HERE/mpv" "$@"
