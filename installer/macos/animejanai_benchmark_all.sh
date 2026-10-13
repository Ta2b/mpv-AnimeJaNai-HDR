#!/bin/sh
# "Run Benchmarks" of the Manager on macOS: the engine comparison of native/macos-bench, run from
# inside the application. Lives in <application>/Contents/Resources/animejanai/benchmarks, which
# the launcher links into the data folder where the Manager looks for it.
#   animejanai_benchmark_all.sh [rapide]
HERE="$(cd -P "$(dirname "$0")" && pwd -P)"
RES="$(cd -P "$HERE/../.." && pwd -P)"
DATA="${ANIMEJANAI_DATA_DIR:-$HOME/Library/Application Support/AnimeJaNai/animejanai}"
export AJI_BENCH_TOOL="$RES/animejanai/inference/animejanai-ort-test"
export AJI_BENCH_MODELS="$RES/animejanai/onnx"
export AJI_BENCH_CONF="$HERE/bench.conf"
export AJI_BENCH_RIFE="$RES/animejanai/rife"
export AJI_BENCH_OUT="$DATA/benchmark-mac.txt"
export AJI_BENCH_WORK="$HOME/Library/Caches/AnimeJaNai/bench"
# The compiled models of the benchmark are kept apart from the player's.
export AJI_ORT_CACHE="$HOME/Library/Caches/AnimeJaNai/bench/models"
exec /bin/bash "$HERE/bench.command" "$@"
