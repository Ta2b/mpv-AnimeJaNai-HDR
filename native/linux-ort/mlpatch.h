// A Core ML model for any tile size, without coremltools.
//
// native/apple/convert_models.py saves each model once, for a template size, with the table of
// where that file stores its sizes (NAME.mlpatch). Every size from 128 to 16383 takes two bytes
// there, so the model for another size is the template with those bytes replaced: the converter
// checks it byte for byte against a real conversion. Portable C++, tested on any machine.
#pragma once
#include <string>

namespace aji {

// Sizes the patch can express: both even, each with its half and its double in 128..16383.
const int kCoreMLMinSide = 256, kCoreMLMaxSide = 8190;

// Writes the package for width x height inputs into `destination` (created; an existing one is
// replaced), from NAME.mlpackage and NAME.mlpatch in `models_dir`. Throws on error.
void write_coreml_package(const std::string &models_dir, const std::string &model, int width, int height,
                          const std::string &destination);

// Changes whenever the template or its table change: part of the cache key of compiled models.
std::string coreml_template_tag(const std::string &models_dir, const std::string &model);

} // namespace aji
