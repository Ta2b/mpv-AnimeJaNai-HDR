#pragma once
#include <filesystem>

namespace aji {
// Returns a verified, content-addressed graph with flow/mask outputs. Copies
// external weights beside it and preserves their relative locations. Throws on
// incomplete inputs/cache or failed writes; never consumes old NAME.flow.onnx.
std::filesystem::path cached_rife_flow(const std::filesystem::path &source,
                                     const std::filesystem::path &cache);
}
