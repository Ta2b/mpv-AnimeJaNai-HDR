# Ordered interpolation stages — Linux CUDA

This bundle contains the project-owned libaji_pipeline.so and aji_pipeline.fatbin.
See GPU-SOURCE.json ordered_pipeline.backend_source for their exact source commit,
and its separate top-level backend_source for the unchanged TensorRT libraries.
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
