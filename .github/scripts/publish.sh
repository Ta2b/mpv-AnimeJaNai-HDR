#!/bin/bash
# Adds one platform's files to the release of a version. Windows, Linux and macOS are released
# independently: the first platform to finish creates the release, the others add to it.
#
# usage: publish.sh VERSION FILE... -- LAST_FILE...
#   The files after "--" go up last. They are the ones an installed copy looks for before it
#   offers the release as an update (overlay archive, AppImage, macOS application): by then
#   everything else it needs is already there.
set -euo pipefail

version="$1"; shift
first=(); last=(); list=first
for file in "$@"; do
    if [ "$file" = "--" ]; then list=last; continue; fi
    if [ "$list" = first ]; then first+=("$file"); else last+=("$file"); fi
done

repo="$GITHUB_REPOSITORY"
if ! gh release view "$version" --repo "$repo" > /dev/null 2>&1; then
    notes="$(dirname "${BASH_SOURCE[0]}")/../release-notes/$version.md"
    note_args=(--notes "mpv-AnimeJaNai HDR $version. Windows, Linux and macOS are published independently: the files of a platform appear when its build succeeds.")
    [ ! -f "$notes" ] || note_args=(--notes-file "$notes")
    # Another platform may create it at the same moment: then the release exists and that is fine.
    gh release create "$version" --repo "$repo" --target "$GITHUB_SHA" --title "$version" --latest=false \
        "${note_args[@]}" \
        || gh release view "$version" --repo "$repo" > /dev/null
fi
[ "${#first[@]}" -eq 0 ] || gh release upload "$version" --repo "$repo" --clobber "${first[@]}"
[ "${#last[@]}" -eq 0 ] || gh release upload "$version" --repo "$repo" --clobber "${last[@]}"
# Promotion is a separate, serialized job shared by all platforms. An older
# build finishing later must not turn an earlier release back into latest.
