#!/bin/bash
# Stage only the project's compiled libraries; vendor runtimes remain separate.
set -euo pipefail
destination="$1"
platform="$2"
# Git Bash receives RUNNER_TEMP as a drive path; tar needs its POSIX form.
if command -v cygpath >/dev/null 2>&1; then destination="$(cygpath -u "$destination")"; fi
if [ ! -s gpu-binaries-source-ref.txt ]; then exit 0; fi
binary_ref="$(tr -d '[:space:]' < gpu-binaries-source-ref.txt)"
[[ "$binary_ref" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid GPU binary source ref' >&2; exit 1; }
case "$platform" in win-x64|linux-x64) ;; *) exit 1;; esac
mkdir -p "$destination"
git fetch --no-tags origin "$binary_ref"
git archive "$binary_ref" "$platform" | tar -x -C "$destination"
staged="$destination/$platform"
# PowerShell and .NET consume the exported path as a native Windows path.
if command -v cygpath >/dev/null 2>&1; then staged="$(cygpath -m "$staged")"; fi
echo "AJI_SPECIALIZED_LOCAL=$staged" >> "$GITHUB_ENV"
