#!/bin/bash
# Stage only the project's compiled libraries; vendor runtimes remain separate.
set -euo pipefail
destination="$1"
platform="$2"
if [ ! -s gpu-binaries-source-ref.txt ]; then exit 0; fi
binary_ref="$(tr -d '[:space:]' < gpu-binaries-source-ref.txt)"
[[ "$binary_ref" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid GPU binary source ref' >&2; exit 1; }
case "$platform" in win-x64|linux-x64) ;; *) exit 1;; esac
mkdir -p "$destination"
git fetch --no-tags origin "$binary_ref"
git archive "$binary_ref" "$platform" | tar -x -C "$destination"
echo "AJI_SPECIALIZED_LOCAL=$destination/$platform" >> "$GITHUB_ENV"
