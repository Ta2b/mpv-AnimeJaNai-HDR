#include "ajm.h"
#include "engine.h"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <sstream>

namespace aji {

AjmModel load_ajm(const std::string &path)
{
    std::ifstream file(path);
    require(file.good(), "Model description not found: " + path);
    AjmModel m;
    std::string line, weights_name, weights_type;
    long weights_count = 0;
    bool header = false;
    while (std::getline(file, line)) {
        std::istringstream in(line);
        std::string word;
        if (!(in >> word)) continue;
        if (word == "AJM") { int version = 0; in >> version; require(version == 1, "Unsupported model description version: " + path); header = true; }
        else if (word == "scale") in >> m.scale;
        else if (word == "weights") in >> weights_name >> weights_type >> weights_count;
        else if (word == "tensors") in >> m.tensors;
        else if (word == "output") in >> m.output;
        else if (word == "op") {
            std::string kind;
            in >> kind;
            AjmOp op;
            in >> op.out;
            auto source = [&] { int t = -1; in >> t; op.in.push_back(t); };
            if (kind == "unshuffle") { op.kind = AjmOp::Unshuffle; source(); in >> op.factor; }
            else if (kind == "shuffle") { op.kind = AjmOp::Shuffle; source(); in >> op.factor; }
            else if (kind == "conv") { op.kind = AjmOp::Conv; source(); in >> op.o >> op.i >> op.k >> op.stride >> op.pad >> op.weight >> op.bias; }
            else if (kind == "relu") { op.kind = AjmOp::Relu; source(); }
            else if (kind == "tanh") { op.kind = AjmOp::Tanh; source(); }
            else if (kind == "sigmoid") { op.kind = AjmOp::Sigmoid; source(); }
            else if (kind == "add") { op.kind = AjmOp::Add; source(); source(); }
            else if (kind == "mul") { op.kind = AjmOp::Mul; source(); source(); }
            else if (kind == "concat") { op.kind = AjmOp::Concat; int n = 0; in >> n; for (int k = 0; k < n; k++) source(); }
            else throw std::runtime_error("Unknown operation '" + kind + "' in " + path);
            require(!in.fail(), "Malformed operation in " + path + ": " + line);
            m.ops.push_back(op);
        }
    }
    require(header && m.tensors > 0 && !m.ops.empty() && m.scale == 2, "Not a 2x model description: " + path);
    require(weights_type == "float16" && weights_count > 0, "Model weights must be half floats: " + path);
    // Every operation reads tensors that exist and writes a new one: the engines rely on it.
    std::vector<char> known((size_t)m.tensors, 0);
    known[0] = 1;
    for (const auto &op : m.ops) {
        require(op.out > 0 && op.out < m.tensors && !known[(size_t)op.out], "Bad tensor numbering in " + path);
        for (int t : op.in) require(t >= 0 && t < m.tensors && known[(size_t)t], "Operation reads an unknown tensor in " + path);
        if (op.kind == AjmOp::Conv)
            require(op.o > 0 && op.i > 0 && op.k > 0 && op.weight >= 0 && op.weight + (long)op.o * op.i * op.k * op.k <= weights_count
                    && op.bias >= 0 && op.bias + op.o <= weights_count && op.stride == 1 && op.pad == (op.k - 1) / 2,
                    "Bad convolution in " + path);
        if (op.kind == AjmOp::Unshuffle) require(op.factor == 2 && op.in[0] == 0, "Unsupported unshuffle in " + path);
        if (op.kind == AjmOp::Shuffle) require(op.factor == 4, "Unsupported shuffle in " + path);
        known[(size_t)op.out] = 1;
    }
    require(m.output > 0 && m.output < m.tensors && known[(size_t)m.output], "Bad output tensor in " + path);
    const std::filesystem::path blob = std::filesystem::path(path).parent_path() / weights_name;
    std::ifstream data(blob, std::ios::binary);
    require(data.good(), "Model weights not found: " + blob.string());
    m.weights.resize((size_t)weights_count);
    data.read((char *)m.weights.data(), (std::streamsize)(m.weights.size() * sizeof(uint16_t)));
    require(data.gcount() == (std::streamsize)(m.weights.size() * sizeof(uint16_t)), "Model weights truncated: " + blob.string());
    return m;
}

int AjmModel::reach() const
{
    // In pixels of the unshuffled image: a k x k convolution reads (k - 1) / 2 further.
    std::vector<int> far((size_t)tensors, 0);
    for (const auto &op : ops) {
        int most = 0;
        for (int t : op.in) most = std::max(most, far[(size_t)t]);
        far[(size_t)op.out] = most + (op.kind == AjmOp::Conv ? (op.k - 1) / 2 : 0);
    }
    // Two input pixels per unshuffled pixel, and one more for the unshuffle itself.
    return 2 * far[(size_t)output] + 2;
}

} // namespace aji
