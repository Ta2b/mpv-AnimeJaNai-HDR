#!/bin/bash
# Player-side Lua checks against a scratch copy of the overlay (same layout as tests/hdr/run.sh). usage: tests/player/run.sh [lua]
P="$(cd "$(dirname "$0")/../.." && pwd)"
OV=$P/BuildMpvUpscale2xAnimeJaNai/mpv-upscale-2x_animejanai/portable_config
LUA=${1:-luajit}
S=$(mktemp -d); mkdir -p $S/portable_config/cache $S/animejanai/inference $S/tmp
cp -r $OV/{hdr-tools,user-scripts,user-shaders,script-opts,profiles} $S/portable_config/
R=$S/portable_config; status=0
run() { local name=$1; shift; printf "%-36s " "$name"; if out=$($LUA $P/tests/player/$name "$@" 2>&1); then echo "${out##*$'\n'}" | cut -c1-140; else status=1; echo "FAIL: $(echo "$out" | tail -3 | tr '\n' ' ' | cut -c1-300)"; fi; }
run interpolation_stages_check.lua $OV/hdr-tools
run legacy_policy_projection_check.lua $OV/hdr-tools $S/tmp
run linux_profile_snapshot_check.lua $R $P/tests/hdr
run interpolation_launch_check.lua $R $P/tests/hdr
run chain_cleanup_launch_check.lua $R $P/tests/hdr $OV linux
rm -rf $S; exit $status
