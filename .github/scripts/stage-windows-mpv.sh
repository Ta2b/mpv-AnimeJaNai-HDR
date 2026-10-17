#!/bin/bash
set -euo pipefail
# No pin means this checkout intentionally uses its previous Windows binaries.
if [ ! -e windows-mpv-source-ref.txt ]; then exit 0; fi
producer="$(tr -d '[:space:]' < windows-mpv-source-ref.txt)"
[[ "$producer" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid Windows mpv producer pin' >&2; exit 1; }
destination="$1"
if command -v cygpath >/dev/null 2>&1; then destination="$(cygpath -u "$destination")"; fi
mkdir -p "$destination"
gh release download "windows-mpv-$producer" --repo "$GITHUB_REPOSITORY" --pattern mpv-windows-x64.7z --dir "$destination"
7z x -y "-o$destination/bundle" "$destination/mpv-windows-x64.7z"
# The assembler verifies source, patch, filter and every binary hash before copy.
staged="$destination/bundle"
if command -v cygpath >/dev/null 2>&1; then staged="$(cygpath -m "$staged")"; fi
echo "MPV_WINDOWS_LOCAL=$staged" >> "$GITHUB_ENV"
