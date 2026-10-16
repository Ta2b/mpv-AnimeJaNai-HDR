# Ordered interpolation stages — experimental Linux CUDA

Project-owned libaji_pipeline.so and aji_pipeline.fatbin, backend source
35c0049ffd2977fe196a34bbbd3b051647486c4d. TRT optional build-status extension
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
No Quality equivalence is claimed. PQ/HLG mixed chains are refused. TrueHDR
retagging is disabled on mixed chains; the unchanged legacy route retains it.

One persistent worker initializes stages and executes with bounded owners,
recorded dependencies and GPU-only canonical YUV444P16 surfaces. Submit and
Complete do not wait for execution or capacity. Typed model build status allows
cancellation of pending stage initialization; lifecycle drains before destruction.
Output flags and counters report API requests/repetitions, not kernel launches.
No CPU pixel copies inside the engine. Stats exclude SDK/TRT workspace memory.

Qualified on RTX4070Ti/Linux: RIFE2->FRUC2->SPAN, cadence/EOF, common RIFE
median exact, legacy fractional pixel/PTS parity, seek/profile/pause, pending
producer, queue cancel/full, controlled final-copy failure and build cancellation.
No other hardware/API, physical presentation or HDR synthesis qualification.
Portable kernels SM75/80/86/89/90/100/120+PTX120; host glibc>=2.38,
GLIBCXX>=3.4.30 (Ubuntu24 package baseline). Source/report in player lot40.
