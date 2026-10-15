# Native MIGraphX + HIP execution

Current target: RX 9070 XT (`gfx1201`). Original ONNX models, fixed tensor shapes,
native MIGraphX graph compilation and HIP video kernels. No additional model
quantization. `fast_math` is disabled. `AJI_MIGRAPHX_TUNE=0` disables exhaustive
kernel tuning; it does not alter the model. Nothing prepares models before use.
`AJI_MIGRAPHX_GRAPH=0` disables HIP graph capture/replay. Unsupported capture
falls back to ordinary network submission. Flow-only RIFE graphs preserve the
weights while removing the unused final RGB output from the compiled graph.

## Linux RGB bridge

Requires ROCm 7.2 with MIGraphX, its runtime dependencies, an AMD-compatible
driver, ONNX Runtime 1.24.1 (the existing shared engine ABI), CMake 3.24+ and a
checkout of the existing configuration parser.

```sh
cmake -S native/linux-ort -B amd-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DAJI_NATIVE_AMD=ON \
  -DORT_ROOT=/path/to/onnxruntime -DAJI_SOURCE=/path/to/animejanai-inference \
  -DROCM_PATH=/opt/rocm -DMIGRAPHX_ROOT=/opt/rocm \
  -DCMAKE_PREFIX_PATH=/opt/rocm -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ \
  -DCMAKE_HIP_COMPILER_ROCM_ROOT=/opt/rocm -DAJI_AMD_ARCHITECTURES=gfx1201
cmake --build amd-build --target aji_migraphx_rgb
```

Install `libaji_migraphx_rgb.so` beside `libaji_ort.so` and its ORT runtime. The
Linux playback script prefers the native library for `backend=MIGraphX`; other
providers continue to load `libaji_ort.so` without ROCm dependencies. Use the
same ROCm SDK/runtime version as the build. The compile-SDK fetcher extracts
only build/link dependencies: it is **not** an AMD runtime installer.

RIFE source conversion, grid, timestep, motion cropping and warp execute on HIP.
Only four bytes of motion amplitude return for the existing pair decision.
Upscaled endpoints are uploaded once per content identity and kept on GPU for
the following instants. This RGB bridge still transfers model images to/from
host memory and keeps its existing RGB24 boundary. It is not a fully resident
video pipeline. Original host behavior and `rife_engine=quality` (legacy `old`) remain available.

## Windows D3D11/D3D12 bridge

The companion inference branch `perf-specialized-gpu-20261014` builds
`aji_migraphx.dll` using `src/aji_dml.cpp` with `AJI_MIGRAPHX_INTEROP=1`.
A standalone AMD build also exists here and needs no CUDA/TensorRT SDK:

```powershell
# Run in an MSVC x64 developer terminal, with CMake/Ninja/Python/7z available.
python native/amd/fetch_windows_sdk.py amd-sdk --runtime
$env:HIP_PATH = (Resolve-Path amd-sdk).Path
$env:HIP_PLATFORM = 'amd'
cmake -S native/amd -B amd-build -G Ninja -DCMAKE_BUILD_TYPE=Release `
  -DAJI_SOURCE=C:/src/animejanai-inference-rtx `
  -DAJI_ORT_ROOT=C:/sdk/ort-directml -DAJI_DML_ROOT=C:/sdk/directml `
  "-DMIGRAPHX_ROOT=$env:HIP_PATH" "-DROCM_PATH=$env:HIP_PATH" `
  "-DCMAKE_PREFIX_PATH=$env:HIP_PATH" -DAJI_AMD_ARCHITECTURES=gfx1201
cmake --build amd-build --target aji aji_migraphx
```

`fetch_windows_sdk.py` pins/checks every archive: ROCm/HIP 10.1 nightly wheels
from **AMD**, MIGraphX 2.18 DLLs/import libraries from the explicitly identified
**community port `lc700x/MIGraphX-Windows`**, C API declarations from the pinned
AMD source. It generates C-consumer export/config headers, retains notices and
writes `AMD-SDK-PROVENANCE.json`. This is not an official AMD MIGraphX Windows
binary pack. The normal HIP SDK 7.2 and Windows ML EP installation are different
distributions and are not interchangeable with these build dependencies.

The private companion's `build-specialized-windows.yml` builds both vendors on
MSVC runners, without tests or inference. Its AMD artifact contains
`inference/aji.dll`, `aji_migraphx.dll`, `AMD-README.md` and the intact SDK/runtime
prefix `inference/amd`. The dispatcher adds the prefix's DLL/tool directories
only when opening MIGraphX; it does not modify the installed system.

The module uses ABI 9, the existing mpv D3D11 video path, the original high-depth
color conversion shaders, shared D3D12/HIP tensors, and two GPU fence directions.
HIP selects the GPU by the Direct3D adapter's LUID. There is no RGB24 host bridge
on this path. Models bind directly to shared input/output allocations when the
compiled graph exposes an output parameter; otherwise only a GPU copy is used.

Pure RIFE and ensemble models keep their original RGB graph. When motion
extraction is unavailable, Windows also keeps that graph. The shipped models
embed their weights; this executor parses model bytes, not external-data models.

RIFE-first `rife_engine=fast` (legacy `new`) estimates motion on source-sized frames and warps
the floating-point upscaled endpoints. Each endpoint is upscaled once, with
the same midpoint/per-instant strategy as the CUDA chain. `rife_engine=quality` (legacy `old`)
keeps the classic pipeline. Windows drawings-timeline spreading is not ported
yet. Temporal rank-5 models are rejected explicitly by this native backend.

Stage the artifact's `inference/` tree in `animejanai/inference`, then select
`backend=MIGraphX`. For an assembled package, pass the extracted bundle root as
`AJI_AMD_LOCAL`. The optional GPU engines component versions these files by
content; its vendor runtime is delivered separately from the small engine DLLs in the
common overlay.
The Manager exposes the Windows choice when both the native module and its
MIGraphX runtime are present; driver compatibility is checked when opening the
model. Linux requires the native module and a matching system ROCm runtime. Baseline DirectML
remains selectable. The complete Windows AMD and NVIDIA DLL builds passed on MSVC runners at
companion source `1f3e8f2` / player source `6a53c39`. Later source changes still
need their own build result, recorded in the precise handoff.
No Windows playback has been run; do not label this backend production-ready.

## Build evidence / continuation

See [the precise handoff](../../docs/CHANTIER-GPU-SPECIALISE.md). Compilation
does not establish numerical equivalence or performance. No tests/benchmarks
were run during this integration at the user's request.
