# Ordered interpolation stages — Linux CUDA

This bundle contains the project-owned libaji_pipeline.so and aji_pipeline.fatbin.
See GPU-SOURCE.json module_sources and ordered_pipeline.module_sources for the
exact source of each artifact. Legacy backend_source is historical; per-module
sources are authoritative.
No NVIDIA SDK/runtime/headers or model weights are redistributed by this feature.

Supported native stages: RIFE TensorRT integer x2..8; spatial ONNX TensorRT;
independent Area CUDA and Spline36 CUDA/TensorRT downscale; final TrueHDR CUDA
with a separately installed Maxine Core + TrueHDR SDK. Spline36 uses the existing
native resize-only chain, without an ONNX model. It runs at the declared position.
Area and Spline36 accept one height ceiling32..8192 or percentage1..100.
Independent Spline36 height preserves source aspect with native even-pixel
rounding, without the legacy16:9 fit-box; Area rounds to the nearest pixel.

FRUC has been removed at user request (AH-328). This bundle no longer contains
its provider, fatbin or setup instructions. Enabled historical FRUC stages fail
explicitly and remain preserved in the profile; disabled entries retain their
options. No implicit replacement occurs. ABI v1 retains reserved fields at their
original offsets to avoid breaking the structure layout; the fields are ignored.

Use chain_N_pipeline_version=1 and ordered stage keys documented in player
sources docs/INTERPOLATION-STAGES.md, with a matching native reader. Maximum16
stages, cumulative factor16, capacity1..2, default owned pixel budget512MiB.
Mixed factors are integer. Equivalent legacy configurations keep ABI9 arithmetic
and rational cadence. Unsupported stages/options/temporal SR fail explicitly.

Consecutive interpolation/upscale stages form logical execution groups.
Compatible TensorRT blocks fuse without reordering stages or RIFE policies.
Fast x4 plus spatial models reuses finished source pictures/motion; Fast x2 keeps
a separate native block because fused alternatives established no benefit.
Multiple RIFE stages may share a group but need separate contexts. Downscale/HDR
are explicit boundaries. Source-view and generation guards protect endpoint
promotion and prefix spatial reuse; reset invalidates both. Attached legacy
resizes are never silently moved by fusion.

The pipeline bridge uses GPU-only canonical YUV444P16. Standalone Spline36 is
qualified against the established native 4:4:4 resize. This does not assert pixel
identity with an old NV12/P010 roundtrip. Faithful migration of a representable
legacy resize->RIFE->upscale chain uses the legacy route; new independent stages
retain their explicit order. No bilinear alias is implemented.

One persistent worker initializes and executes stages with bounded ownership.
Submit/Complete do not wait for execution or capacity. Typed build status allows
cancellation of pending model initialization; destruction drains the lifecycle.
Counters describe API requests, not kernel launches. The engine makes no CPU
pixel copies; the budget excludes internal TensorRT/SDK workspace.

Only one HDR stage is allowed per profile, inactive stages included. Current
interpolation/upscale providers require SDR; TrueHDR must be last. Its SDK input
is SDR709 RGBA8; output RGB10A2 PQ2020 is exported as limited YUV444P16 with10
effective SDK bits. Converted metadata is published only after SDK success.
Target peak400..2000nits is a user target, not fabricated MaxCLL. An HDR-only chain
passes native PQ/HLG BT2020 through without conversion. SDK staging buffers count
toward the pixel budget, SDK internal workspace does not. The mpv render HDR mode
is managed by the player, not advertised as this CUDA provider.

Portable kernels target SM75/80/86/89/90/100/120+PTX; host glibc>=2.38,
GLIBCXX>=3.4.30. Compilation for these targets is not per-device qualification.
Lot57 on Linux RTX4070Ti: removal preserves all5 output hashes, PTS, durations,
flags, dimensions and request counters for Area(identity)->RIFE Fast4->SPAN;
fusion trace remains active, same TRT and fatbin. Spline36 model-free128x72->64x36
is bit-exact to ABI9 YUV444P16 with padding, descriptors, owners and timeline
preserved. No legacy420 equivalence, universal FPS or physical HDR claim.
Historical fusion/Area/TrueHDR qualification remains in player lots47/48/55;
FRUC historical evidence no longer describes an available provider.

AH-360: exact Area3:2 specialization uses integer (2,1)/(1,2) weights and
(sum+4)/9. One 1920x1080->1280x720 YUV444P16 case covering all65536 codes:
2764800 output values exact to previous generic Area and integer oracle;
crops/strides/padding/descriptors/owners preserved. Generic other ratios stay
unchanged. This removes generic FP64 footprint work, not a measured FPS claim.

AH-361: Quality requires configured RIFE semantics-v1 from the same loaded
image as create/configure/process. Missing or inconsistent semantics refuse
Quality before pixels (missing API: before create/build). Existing local files
are preserved; update GPU components and restart the player. Explicit Fast
remains compatible with older modules and reports effective=unknown. A loaded
symbol path and optional declared source are not a hash of mapped pages.
Qualification covers initialization/guards, no video replay/FPS gain. Numeric
GPU sections are identical to prior qualified code. This applies only to the
ordered CUDA pipeline, not historical ABI9/dispatcher or other OS.

Lot A (AH-55, AH-372, AH-371, AH-373): the pipeline lends its stream to the
TensorRT engine (aji_surface_set_stream_v1) so canonical conversion, Area,
inference and output copies are ordered by the GPU; isolated jobs run as a
one-job batch; the TrueHDR SDK stays on the default stream, which carries nothing else: one
host wait for the pack, asynchronous run, unpack ordered by event
(AJI_HDR_STREAM_MODE=null-async-packwait, the default; null-async-events keeps
no host wait but makes the default stream, shared with mpv's CUDA interop,
wait for the whole inference). Environment switches, for comparison only: AJI_PIPELINE_SHARED_STREAM=0
(private streams and host waits), AJI_HDR_STREAM_MODE=legacy or
AJI_HDR_LEGACY_STREAM=1 (SDK reference: default stream, synchronous run, three
host waits), AJI_RIFE_MATRIX_709=1 (ignore the pair's colour matrix),
AJI_RIFE_PAD=16|32|64 (RIFE 4.26 needs 64). Modes that run the SDK on the
pipeline stream produce wrong pixels with TrueHDR 1.2.3 and are refused unless
AJI_HDR_UNSAFE_MODES=1 (evidence only).
