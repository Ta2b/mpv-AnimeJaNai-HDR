# Ordered interpolation stages — experimental Linux CUDA

Project-owned libaji_pipeline.so and aji_pipeline.fatbin, backend source
9f2541e3dee1f159800b3a20c0e0729adc18491b. TRT optional build-status extension
comes from 79e8aa48e0c776e8335c2430d538426ed3b0a506 (same TRT sources at 35c0049).
No NVIDIA SDK/runtime/headers or model weights are included by this feature.

Opt in with chain_N_pipeline_version=1 and ordered stage keys, as documented
in docs/INTERPOLATION-STAGES.md. Requires the matching ordered-pipeline1 Linux
mpv filter; existing profiles keep their original arithmetic and rational cadence.
RIFE TensorRT x2..8, FRUC CUDA Fast x2, spatial ONNX TensorRT can be ordered.
Cumulative factor <=16, <=16 stages, capacity1..2, owned pixel budget512MiB.
Mixed factors currently integer; exact-equivalent legacy RIFE fractions remain
on ABI9. Unsupported stages/options/temporal SR fail explicitly, never vanish.

FRUC requires explicit paths to separately installed libNvOFFRUC.so and its
compatible CUDA runtime (SDK5.0.7 uses CUDART11). The stage kernel_fatbin path must point explicitly
to the bundled aji_fruc.fatbin. Never rename CUDART13 to11. FRUC is internally8bit SDR,
with known jagged/mouth/occlusion defects and nonconclusive SDK repeatability.
No Quality equivalence is claimed. Current interpolation/upscaling providers
require SDR input. HDR output requires an explicit final TrueHDR stage; no
request alone retags SDR pictures.

One persistent worker initializes stages and executes with bounded owners,
recorded dependencies and GPU-only canonical YUV444P16 surfaces. Submit and
Complete do not wait for execution or capacity. Typed model build status allows
cancellation of pending stage initialization; lifecycle drains before destruction.
Output flags and counters report API requests/repetitions, not kernel launches.
No CPU pixel copies inside the engine. Stats exclude SDK/TRT workspace memory.

Qualified on RTX4070Ti/Linux: RIFE2->FRUC2->SPAN, cadence/EOF, common RIFE
median exact, legacy fractional pixel/PTS parity, seek/profile/pause, pending
producer, queue cancel/full, controlled final-copy failure and build cancellation.
No other hardware/API or physical presentation qualification.
Portable kernels SM75/80/86/89/90/100/120+PTX120; host glibc>=2.38,
GLIBCXX>=3.4.30 (Ubuntu24 package baseline). Source/report in player lot40.


Independent Downscale: resize/area/cuda, target_height32..8192 or exclusive
integer target_percent1..100. Shrinks only, aspect rounded to the nearest pixel,
GPU YUV444P16 area integration, no RGB8 conversion or cadence change. Static
aji_pipeline_features_v1 advertises AREA_DOWNSCALE without GPU initialization.
At most one HDR stage per profile (all chains, inactive stages included).
The optional HDR conversion capability is described below.
Qualified: 1080->720 and1080->540 independent area references max0 YUV16 code,
ROI/owners/EOF; actual NVDEC Area720->RIFE720 five outputs/PTS/durations; original
endpoints exact across RIFE1080->Area720 and Area720->RIFE720. Synthesized
contours differ with resolution. Performance qualification remains partial:
short timings varied; no universal FPS claim. Source/report in player lot47.


Explicit TrueHDR: hdr/nvidia-truehdr/cuda, factor1, Quality configuration with
contrast0..200, saturation0..200, middle_gray10..100 and peak400..2000nits.
Requires externally installed NVIDIA Maxine Core + TrueHDR feature and their
CUDA12/NPP/TensorRT10 dependencies; no vendor SDK binary/header is distributed.
Default installed root /usr/local/VideoFX (or ANIMEJANAI_VFX_SDK); managed ZIP
import is tracked separately. The portable launcher supplies SDK library paths.
A matching hdr-stage1 reader negotiates color via aji_pipeline_output_color_v1;
older readers refuse HDR before processing. Per-pipeline effects run on the
worker; SDK default stream and producer/completion fences are required by the
acquired reference. Pixel conversion: SDR BT.709 -> RGBA8 SDK input -> RGB10A2
PQ BT.2020 -> limited YUV444P16, 10 effective SDK bits. Converted frames are
released/tagged only after successful SDK completion. Target peak is a configured
display target, never fabricated content MaxCLL. The stage must be last because
the current other providers require SDR. An HDR-only chain passes native
PQ/HLG BT.2020 through, preserving source HDR metadata and avoiding conversion.
The SDK staging buffers count toward the pixel budget; SDK workspace does not.

Qualified Linux RTX4070Ti: independent acquired SDK gradient/primary reference,
pack bytes exact, unpack <=1 YUV16 code, complete pipeline output max0 against
that reference, reset creates a fresh effect, owners/EOF/timestamps balanced,
old reader explicitly refused. Native HDR passthrough bit-exact, no HDR-converted
flag. Actual NVDEC RIFE->TrueHDR and RIFE->FRUC->TrueHDR produce five frames each,
exact native PTS/durations/EOF; latter export has PQ/BT.2020 limited metadata.
Matroska export timestamps have millisecond rounding and final muxed duration
limits; this is distinct from exact native playback duration. No FPS gain,
physical HDR display, Windows/macOS HDR-stage or other-GPU qualification claimed.
