/* Internal: a copy of a RIFE 4.x model that also outputs its motion field and its mask. */
#pragma once

#include <string>
#include <vector>

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
