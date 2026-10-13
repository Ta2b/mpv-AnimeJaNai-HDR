// NAME.ajm / NAME.ajw: a 2x SPAN model as a list of operations and its weights in half floats,
// written by native/apple/convert_models.py. Read by the Metal engine and by the reference
// executor of the tests; the core reads it for the reach of the model (tile overlap).
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace aji {

struct AjmOp {
    enum Kind { Unshuffle, Conv, Relu, Tanh, Sigmoid, Add, Mul, Concat, Shuffle } kind;
    int out = 0;
    std::vector<int> in;      // source tensors
    // Conv: out channels, in channels, kernel, stride, padding, weight and bias offsets (in values)
    int o = 0, i = 0, k = 0, stride = 1, pad = 0;
    long weight = 0, bias = 0;
    int factor = 0;           // Unshuffle / Shuffle
};

struct AjmModel {
    int tensors = 0, output = 0, scale = 2;
    std::vector<AjmOp> ops;
    std::vector<uint16_t> weights;   // half floats

    // Rows and columns of the input a pixel of the output can depend on, on each side: what a
    // tile must see past its own edges to give the same result as the whole frame.
    int reach() const;
    // Multiplications for one pixel of the unshuffled image: to compare two models' costs.
    double cost() const;
};

// Throws std::runtime_error with the reason.
AjmModel load_ajm(const std::string &path);

} // namespace aji
