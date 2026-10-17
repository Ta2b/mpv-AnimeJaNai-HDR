#!/usr/bin/env bash
# Build the SDR Vulkan backend; no CUDA/TensorRT or Python runtime at playback.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(realpath -m "${1:?usage: build-inference.sh WORK OUTPUT ONNX_DIRECTORY}")"
OUTPUT="$(realpath -m "${2:?output directory required}")"
ONNX="$(realpath "${3:?original ONNX directory required}")"
PYTHON="${AJ_PYTHON:-python3}"
mkdir -p "$WORK" "$OUTPUT/inference" "$OUTPUT/onnx" "$OUTPUT/rife-vulkan" "$OUTPUT/licenses"
clone() {
    local repository="$1" directory="$2" revision="$3"
    if [ ! -d "$directory/.git" ]; then git clone --filter=blob:none "$repository" "$directory"; fi
    git -C "$directory" checkout --detach "$revision"
}
clone https://github.com/Tencent/ncnn.git "$WORK/ncnn-source" d8227bbe4f0357640319a69660fe399664d8acc0
git -C "$WORK/ncnn-source" submodule update --init --recursive
clone https://github.com/nihui/rife-ncnn-vulkan.git "$WORK/rife-source" a7532fc3f9f8f008cd6eecd6f2ffe2a9698e0cf7
clone https://github.com/the-database/animejanai-inference.git "$WORK/inference-source" v0.11.1
cmake -S "$REPO/native/linux-vulkan" -B "$WORK/vulkan-build" -DCMAKE_BUILD_TYPE=Release \
    -DNCNN_SOURCE="$WORK/ncnn-source" -DRIFE_SOURCE="$WORK/rife-source" -DAJI_SOURCE="$WORK/inference-source"
cmake --build "$WORK/vulkan-build" -j "${AJ_BUILD_JOBS:-4}"
cp "$WORK/vulkan-build/libaji_vulkan.so" "$WORK/vulkan-build/animejanai-vulkan-test" "$OUTPUT/inference/"
# libgomp is bundled; the Vulkan loader and drivers must come from the host.
libgomp="$(ldd "$WORK/vulkan-build/libaji_vulkan.so" | awk '/libgomp.so.*=>/ {print $3}')"
[ -n "$libgomp" ] && cp -L "$libgomp" "$OUTPUT/inference/libgomp.so.1"
cp -r "$WORK/rife-source/models/rife-v4.6" "$OUTPUT/rife-vulkan/"
for source in "$ONNX/"*SPANF3*.onnx; do
    [ -f "$source" ] || continue
    "$PYTHON" "$REPO/native/linux-vulkan/convert_span.py" "$source" "$OUTPUT/onnx/$(basename "${source%.onnx}").ncnn"
done
test -f "$OUTPUT/onnx/2x_AnimeJaNai_HD_V3.1Sharp1_Performance_SPANF3_b5f48_unshuffle_fp16.ncnn.param"
cp "$WORK/ncnn-source/LICENSE.txt" "$OUTPUT/licenses/NCNN.txt"
cp "$WORK/rife-source/LICENSE" "$OUTPUT/licenses/RIFE-NCNN-Vulkan.txt"
printf 'Configuration parser: the-database/animejanai-inference v0.11.1, src/aji_conf.{cpp,h}\nhttps://github.com/the-database/animejanai-inference/tree/v0.11.1\nThe tagged source contains no standalone license file.\n' > "$OUTPUT/licenses/AnimeJaNai-Inference.txt"
cp "$WORK/ncnn-source/glslang/LICENSE.txt" "$OUTPUT/licenses/glslang.txt"
printf 'vulkan_bridge_abi=1\nncnn=d8227bbe4f0357640319a69660fe399664d8acc0\nrife=a7532fc3f9f8f008cd6eecd6f2ffe2a9698e0cf7\nrife_model=4.6\nrife_input_cache=aji-v1\nsource_ids=aji-v1\naji_conf=v0.11.1\nspan_converter=span-direct-v1\nspan_resident=aji-v1\nspan_boundary=f32-denorm-norm-v1\n' > "$OUTPUT/inference/vulkan-build-info.txt"
echo "VULKAN_LOCAL=$OUTPUT"
