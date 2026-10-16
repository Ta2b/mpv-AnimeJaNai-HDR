// Portable, framed cache contract. Native consumers supply observed metadata.
#pragma once
#include "content_identity.h"

namespace aji::identity {
enum class ProgramFormat { OnnxExport, TensorRT, CoreML, OrtProvider, MIGraphX };
enum class IoPolicy { SourceDefined, Specialized };
struct Binding {
    std::string name, type;
    std::vector<int64_t> dimensions; // -1 is a symbolic/dynamic extent
};
struct Program {
    ProgramFormat format = ProgramFormat::OnnxExport;
    std::string source_scheme, source_digest; // graph AND every external resource
    std::string converter;
    uint64_t converter_version = 0;
    std::string options; // exact effective options, including precision overrides
    std::string build_environment; // explicit builder environment prefix, if any
    IoPolicy io_policy = IoPolicy::SourceDefined;
    std::vector<Binding> bindings; // all specialization/override bindings
    std::string compiler, runtime, device;
};

inline const char *format_name(ProgramFormat format)
{
    switch (format) {
    case ProgramFormat::OnnxExport: return "onnx-export";
    case ProgramFormat::TensorRT: return "tensorrt-plan";
    case ProgramFormat::CoreML: return "coreml-program";
    case ProgramFormat::OrtProvider: return "ort-provider-program";
    case ProgramFormat::MIGraphX: return "migraphx-program";
    }
    throw std::invalid_argument("Unknown program cache format");
}

inline std::string program_key(Program p)
{
    const auto format = format_name(p.format);
    auto require = [](bool ok, const char *why) { if (!ok) throw std::invalid_argument(why); };
    require(!p.source_scheme.empty(), "Program source scheme missing");
    require(p.source_digest.size() == 64 && std::all_of(p.source_digest.begin(), p.source_digest.end(),
        [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); }), "Program source SHA-256 invalid");
    require(!p.converter.empty() && p.converter_version != 0, "Program converter/version missing");
    require(p.io_policy == IoPolicy::SourceDefined || p.io_policy == IoPolicy::Specialized,
            "Unknown program I/O policy");
    require((p.io_policy == IoPolicy::SourceDefined) == p.bindings.empty(),
            "Program I/O specialization must declare its bindings");
    if (p.format == ProgramFormat::OnnxExport)
        require(p.compiler.empty() && p.runtime.empty() && p.device.empty(),
                "Portable ONNX export cannot depend on runtime/device");
    else
        require(!p.compiler.empty() && !p.runtime.empty() && !p.device.empty(),
                "Compiled program compiler/runtime/device compatibility missing");
    std::sort(p.bindings.begin(), p.bindings.end(), [](const Binding &a, const Binding &b) { return a.name < b.name; });
    Sha256 hash;
    hash.text("animejanai-program-key-v3"); hash.text(format);
    hash.text(p.source_scheme); hash.text(p.source_digest);
    hash.text(p.converter); hash.integer(p.converter_version); hash.text(p.options); hash.text(p.build_environment);
    hash.text(p.io_policy == IoPolicy::SourceDefined ? "source-defined" : "specialized");
    hash.integer(p.bindings.size());
    std::string previous;
    for (const auto &binding : p.bindings) {
        require(!binding.name.empty() && binding.name != previous && !binding.type.empty()
                && !binding.dimensions.empty(), "Invalid or duplicate program I/O binding");
        previous = binding.name;
        hash.text(binding.name); hash.text(binding.type); hash.integer(binding.dimensions.size());
        for (auto dim : binding.dimensions) {
            require(dim == -1 || dim > 0, "Invalid program I/O dimension");
            hash.integer(static_cast<uint64_t>(dim));
        }
    }
    hash.text(p.compiler); hash.text(p.runtime); hash.text(p.device);
    return hash.hex();
}
} // namespace aji::identity
