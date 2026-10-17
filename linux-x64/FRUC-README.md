# NVIDIA FRUC provider — experimental Fast, Linux CUDA

This bundle contains the project-owned libaji_fruc.so and aji_fruc.fatbin.
It contains NO NVIDIA Optical Flow SDK header/library/runtime and NO weights.
Install the NVIDIA Optical Flow SDK separately under its own license.

The provider is opt-in through include/fruc.h / include/interpolator.h in
Ta2b/animejanai-inference-rtx, source 4603933f363bc35ab2bcfab433ae665e7d4b7397. Explicit absolute paths are required
for the user SDK libNvOFFRUC.so, its compatible CUDA runtime (SDK5.0.7 uses
libcudart.so.11.0), and the bundled aji_fruc.fatbin. Never rename CUDART13 to11.
A borrowed CUDA context must stay alive until destroy; NULL retains the primary
context. Create/reset/drain/destroy are blocking lifecycle operations; run them
outside the UI. Submit and Complete do not wait for pixel execution/capacity.
Owner callbacks and recorded producer CUDA events follow interpolator.h.

Negotiated subset: 2 inputs, 1 scalar median (x2), bounded worker1–4 jobs,
CUDA RGB8/full, NV12/left SDR or YUV444P16 input; RGB8 or YUV444P16 output.
FRUC synthesizes at 8-bit precision even with a 16-bit YUV container. PQ/HLG,
P010, other phases, rotations, foreign devices and CPU surfaces are refused.
Quality/default RIFE is preserved. SDK repetitions are reported separately.

Qualified locally: RTX4070Ti, Linux, SDK5.0.7, CUDA13.4/driver615.78.08;
colors/crops/padding/PTS, owned adjacent buffers, dependency/cancel/seek/error,
and direct GPU FRUC->SPAN. Portable kernels target SM75/80/86/89/90/100/120
plus PTX120, which is compilation coverage, not other-hardware qualification.
Host binary needs glibc>=2.34 and GLIBCXX_3.4.30. SDK availability is separate.

Exact pixel reproducibility remains nonconclusive: the unchanged standalone
SDK prototype itself varied on a short controlled repeat. Jagged contours and
mouth/occlusion defects remain visible. This is experimental Fast, not Quality.
The player pipeline/Manager stage editor is a separate integration (AH-301/302).
See docs/qualification/lot-39-fruc-native-20261016.md in player source releases.

Artifact protection (create flag PROTECT_ARTIFACTS=2, static feature mask1) is
opt-in at provider level, on by default in the Fast stage. Integer GPU bright-edge
energy above twice the maximum source energy rejects the synthesis. Matching
source/output descriptors copy the previous source exactly, including YUV16,
without an RGB8 round trip. Only 24 bytes of counters cross to CPU; no pixels.
Completion flags distinguish protection from SDK repetitions; optional protection
stats count checked/rejected frames. This sacrifices local fluidity, cannot repair
the SDK itself and does not detect every possible defect. artifact_protection=no
explicitly restores standard FRUC. Quality/RIFE and model binaries are untouched.

Qualified severe beam case: GPU and independent CPU integer sums identical;
ratio2.757 rejects, ordinary acquired control ratio1.045 stays untouched. Metric
GPU interval0.080ms1080p /0.033ms720p, isolated observations, no FPS claim. Native
and actual NVDEC player show source/protected/EOF pixels exact, three outputs,
PTS0/20.5/41ms and durations20.5/20.5/41ms; output flag140 identifies protection.
Other motion/hardware remains unqualified. Source/report player lot52.
