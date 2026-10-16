#pragma once
#include <onnxruntime_c_api.h>
namespace aji {
// Domain/operator live as long as this library; no manual API reinitialization.
void register_cpu_activations(OrtSessionOptions *options);
}
