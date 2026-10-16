/* Internal: a copy of a RIFE 4.x model that also outputs its motion field and its mask. */
#pragma once

#include <string>
#include <vector>
#include <array>
#include <cstdint>

enum class AjiFixedShape { Unchanged, Specialized, Unsupported, Invalid };
// Only graph-input type/shape metadata is edited. Nodes, weights, outputs and
// external locations retain their exact bytes. No guessed layout or symbol name.
AjiFixedShape aji_onnx_fixed_rank4_input(const std::vector<char> &model,
    const std::array<int64_t, 4> &shape, std::vector<char> *out, std::string *why);
// Content-qualified RIFE4.26 image/flow graphs only. Keep weights and all
// unrelated nodes/metadata; expose native FLOAT activations between explicit casts.
bool aji_onnx_cpu_activations(const std::vector<char> &model, std::vector<char> *out, size_t *count);

// RIFE's picture is warp(img0, flow0) * mask + warp(img1, flow1) * (1 - mask), nothing else.
// With the flow ([1, 4, H, W], in pixels: channels 0-1 towards img0, 2-3 towards img1) and the
// mask ([1, 1, H, W], weight of img0) as outputs, the same warp and blend can be applied to
// other pictures of the same scene: their upscaled versions. Weights and graph are untouched;
// two graph outputs are added. Returns false (with a reason) when the model does not have the
// expected structure.
bool aji_onnx_add_flow_outputs(const std::vector<char> &model, std::vector<char> *out,
                               std::string *why);
// Motion-only execution: keep all nodes/weights, expose only flow and mask.
// The compiler can remove the unused final RGB warps without changing motion.
bool aji_onnx_motion_outputs(const std::vector<char> &model, std::vector<char> *out,
                             std::string *why);
// Every external weight location (including nested graphs, sparse tensors and
// local functions), deduplicated. Malformed metadata is rejected.
bool aji_onnx_external_locations(const std::vector<char> &model, std::vector<std::string> *locations,
                                  std::string *why);
