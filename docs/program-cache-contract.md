# Program cache identity contract v3

`program_identity.h` is the same portable C++17 implementation in the backend and the player's native/common directory. It serializes tagged fields with SHA-256 length framing; named bindings are sorted and duplicates/unknown policies/missing required compatibility data fail closed. A source digest is a digest of the complete graph/package and every external resource, with its own explicit scheme. A model filename, mtime or path is not content identity.

Required fields: artifact format; source scheme and SHA-256; converter name and nonzero semantic version; exact effective build options and explicit builder environment; I/O policy; compiler, runtime and device compatibility for compiled artifacts. Specialized bindings carry names, types and ordered dimensions (-1 means dynamic). With source-defined I/O, all declared types, output shapes and flexible constraints come from the content-identified graph/package, and every external specialization/precision override must occur in the hashed options. Unknown values must be rejected by a native adapter, never replaced with an optimistic compatibility token.

| Format | I/O dependency | Compatibility dependencies |
|---|---|---|
| Portable ONNX export | Graph types/shapes plus explicit transform options | Compiler/runtime/device fields must be empty; export semantics are converter+version |
| TensorRT plan | Typed ONNX plus complete min/opt/max profiles, I/O formats and precision options | TensorRT/compiler build, CUDA runtime/driver compatibility, GPU UUID/SM |
| Core ML compiled program | Complete package shapes/types/flexible constraints, conversion options and compute units | Converter/compiler version, OS/Core ML compatibility and compute-device policy |
| ORT provider program | Complete ONNX, provider options, shape/type overrides and precision | ORT + provider/compiler version, provider device/driver compatibility |
| MIGraphX program | Complete ONNX, shape/type/quantization/compile options | MIGraphX + ROCm compiler/runtime, target GPU/driver compatibility |

The common contract defines these policies; it does not discover native API metadata. Native Core ML adoption/qualification is AH-240, ORT/MIGraphX AH-241, complete derived/temporal TRT audit AH-242. Metadata fixtures for these formats are not native execution qualification.

## Current consumers

Ordinary TensorRT uses `onnx-source-v2` (graph and all external weights), `onnx-to-tensorrt` semantic version 1, exact settings plus the explicit trtexec environment, runtime/header-build/CUDA/driver token and observed GPU token. Its bundled trtexec matches the pinned TensorRT toolchain; replacing it with an incompatible compiler is unsupported, not an inferred compatible cache hit. Types and output constraints are source-defined; build profiles and I/O overrides are in the settings. Playback dimensions within a dynamic profile do not generate another compiled key. File locations, stats settings and playback colour conversion are not compilation dependencies.

The flow export uses that same source scheme, `rife-flow-outputs` semantic version 2 and the portable policy. It remains independent of runtime, GPU and playback dimensions, preserving byte-identical graph/weights. No new arithmetic or precision is introduced.

## Migration

The outer schema is `animejanai-program-key-v3`. TensorRT files are `aji-v3-<sha256>.engine`; flow exports live in `rife-flow-v3/<sha256>/`. Prior v2 files/directories are preserved and not imported under the new contract. Each first request creates a new artifact through the existing transaction/key-lock/recovery protocol; subsequent requests reuse it. This is an intentional one-time rebuild/re-export cost, not an FPS optimization. Bump converter semantic version only when transformation semantics change; bump the outer schema for a contract/serialization change. Do not hash the whole application Git SHA and invalidate caches for unrelated edits.
