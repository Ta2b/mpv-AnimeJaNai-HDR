#!/bin/bash
# Finds the most recent earlier release that has this platform's pack index, so that component
# packs (several GB) unchanged since then are neither built nor uploaded again. The assembler
# reads the two variables written here.
#
# usage: previous-packs.sh VERSION INDEX_NAME     (packs.json or packs-linux-x64.json)
set -uo pipefail

version="$1"; index="$2"
repo="$GITHUB_REPOSITORY"
for tag in $(gh release list --repo "$repo" --limit 20 --json tagName --jq '.[].tagName'); do
    [ "$tag" = "$version" ] && continue
    rm -rf reuse-packs && mkdir reuse-packs
    gh release download "$tag" --repo "$repo" --dir reuse-packs \
        --pattern 'packs*.json' --pattern 'manifest*.json' > /dev/null 2>&1 || continue
    [ -s "reuse-packs/$index" ] || continue
    echo "ANIMEJANAI_REUSE_PACKS_DIR=$GITHUB_WORKSPACE/reuse-packs" >> "$GITHUB_ENV"
    echo "ANIMEJANAI_REUSE_PACKS_URL=https://github.com/$repo/releases/download/$tag" >> "$GITHUB_ENV"
    echo "Reusing unchanged packs from $tag."
    exit 0
done
echo "No earlier release has $index: every pack is built."
