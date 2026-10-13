#!/bin/sh
# Linux analogue of animejanai_benchmark_all.bat: runs the cross-platform
# AnimeJaNaiBenchmark tool against this install's bundled clips + benchmark slots.
# The Manager's "Run Benchmarks" button calls it and shows what it prints.
HERE="$(cd "$(dirname "$0")" && pwd)"   # animejanai/benchmarks
ROOT="$(cd "$HERE/../.." && pwd)"       # install root (AppImage: the writable data folder)
# bundled mpv + inference libs on the loader path
export LD_LIBRARY_PATH="$ROOT/mpv:$ROOT/animejanai/inference:${LD_LIBRARY_PATH:-}"
exec "$HERE/AnimeJaNaiBenchmark" --install-root "$ROOT" "$@"
