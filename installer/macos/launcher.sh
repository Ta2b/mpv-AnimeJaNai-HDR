#!/bin/sh
# Main executable of "mpv AnimeJaNai.app". mpv does not read settings from its bundle, so the
# settings live in ~/Library/Application Support/AnimeJaNai/mpv (MPV_HOME), apart from a personal
# mpv setup. The script is refreshed from the application at every launch; mpv.conf and the
# options file are only created when missing, so that edits are kept.
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"
DATA="$HOME/Library/Application Support/AnimeJaNai"
mkdir -p "$DATA/mpv/scripts" "$DATA/mpv/script-opts" "$HOME/Library/Caches/AnimeJaNai"
[ -f "$DATA/mpv/mpv.conf" ] || cp "$RES/animejanai-config/mpv.conf" "$DATA/mpv/mpv.conf"
[ -f "$DATA/mpv/script-opts/animejanai_mac.conf" ] || \
    cp "$RES/animejanai-config/script-opts/animejanai_mac.conf" "$DATA/mpv/script-opts/animejanai_mac.conf"
cp -f "$RES/animejanai-config/scripts/animejanai_mac.lua" "$DATA/mpv/scripts/animejanai_mac.lua"
export MPV_HOME="$DATA/mpv"
export ANIMEJANAI_BUNDLE="$RES"
exec "$HERE/mpv" "$@"
