// Executor: the model description (NAME.ajm) run in plain C++, single floats. Far too slow for
// playback; it exists so that the description read by the Metal engine, and everything the core
// does around an executor, can be checked on any machine against ONNX Runtime.
#include "engine.h"
#include "ajm.h"
#include <cmath>
#include <cstring>

namespace aji {
namespace {

float half_to_float(uint16_t h)
{
    const uint32_t sign = (uint32_t)(h & 0x8000) << 16;
    uint32_t exponent = (h >> 10) & 0x1F, mantissa = h & 0x3FF, bits;
    if (exponent == 0) {
        if (mantissa == 0) bits = sign;
        else {
            exponent = 1;
            while (!(mantissa & 0x400)) { mantissa <<= 1; exponent--; }
            bits = sign | ((exponent + 112) << 23) | ((mantissa & 0x3FF) << 13);
        }
    } else if (exponent == 31) bits = sign | 0x7F800000u | (mantissa << 13);
    else bits = sign | ((exponent + 112) << 23) | (mantissa << 13);
    float f;
    std::memcpy(&f, &bits, sizeof f);
    return f;
}

struct Planes {
    int c = 0, w = 0, h = 0;
    std::vector<float> v;
    Planes() = default;
    Planes(int channels, int width, int height) : c(channels), w(width), h(height), v((size_t)channels * width * height) {}
    float *at(int channel) { return v.data() + (size_t)channel * w * h; }
    const float *at(int channel) const { return v.data() + (size_t)channel * w * h; }
};

class ReferenceExecutor : public Executor {
public:
    explicit ReferenceExecutor(const ExecutorRequest &r) : w_(r.width), h_(r.height)
    {
        model_ = load_ajm(r.models_dir + "/" + r.model + ".ajm");
        weights_.resize(model_.weights.size());
        for (size_t i = 0; i < weights_.size(); i++) weights_[i] = half_to_float(model_.weights[i]);
        label = "Reference/CPU";
    }

    void run(const Job &job) override
    {
        std::vector<Planes> t((size_t)model_.tensors);
        Planes &rgb = t[0] = Planes(3, w_, h_);
        for (int y = 0; y < h_; y++) {
            const uint8_t *row = job.in + (ptrdiff_t)y * job.in_stride;
            for (int x = 0; x < w_; x++)
                for (int k = 0; k < 3; k++) rgb.at(k)[(size_t)y * w_ + x] = row[3 * x + k] * (1.0f / 255.0f);
        }
        for (const auto &op : model_.ops) {
            const Planes &a = t[(size_t)op.in[0]];
            Planes &d = t[(size_t)op.out];
            switch (op.kind) {
            case AjmOp::Unshuffle:
                // out[c*4 + dy*2 + dx, y, x] = in[c, 2y + dy, 2x + dx]
                d = Planes(a.c * 4, a.w / 2, a.h / 2);
                for (int c = 0; c < a.c; c++)
                    for (int dy = 0; dy < 2; dy++)
                        for (int dx = 0; dx < 2; dx++)
                            for (int y = 0; y < d.h; y++)
                                for (int x = 0; x < d.w; x++)
                                    d.at(c * 4 + dy * 2 + dx)[(size_t)y * d.w + x] = a.at(c)[(size_t)(2 * y + dy) * a.w + 2 * x + dx];
                break;
            case AjmOp::Shuffle: {
                // out[c, y*r + dy, x*r + dx] = in[c*r*r + dy*r + dx, y, x]
                const int r = op.factor;
                d = Planes(a.c / (r * r), a.w * r, a.h * r);
                for (int c = 0; c < d.c; c++)
                    for (int dy = 0; dy < r; dy++)
                        for (int dx = 0; dx < r; dx++)
                            for (int y = 0; y < a.h; y++)
                                for (int x = 0; x < a.w; x++)
                                    d.at(c)[(size_t)(y * r + dy) * d.w + x * r + dx] = a.at(c * r * r + dy * r + dx)[(size_t)y * a.w + x];
                break;
            }
            case AjmOp::Conv: {
                require(a.c == op.i, "Reference: channel count mismatch");
                d = Planes(op.o, a.w, a.h);
                const float *weight = weights_.data() + op.weight, *bias = weights_.data() + op.bias;
                const int k = op.k, pad = op.pad, w = a.w, h = a.h;
                parallel((size_t)op.o, 1, [&, weight, bias, k, pad, w, h](size_t first, size_t last) {
                    for (size_t o = first; o < last; o++) {
                        float *out = d.at((int)o);
                        std::fill(out, out + (size_t)w * h, bias[o]);
                        for (int i = 0; i < op.i; i++) {
                            const float *in = a.at(i);
                            for (int ky = 0; ky < k; ky++)
                                for (int kx = 0; kx < k; kx++) {
                                    const float f = weight[((o * op.i + i) * k + ky) * k + kx];
                                    const int oy = ky - pad, ox = kx - pad;
                                    for (int y = std::max(0, -oy); y < std::min(h, h - oy); y++) {
                                        const float *src = in + (size_t)(y + oy) * w;
                                        float *dst = out + (size_t)y * w;
                                        for (int x = std::max(0, -ox); x < std::min(w, w - ox); x++) dst[x] += f * src[x + ox];
                                    }
                                }
                        }
                    }
                });
                break;
            }
            case AjmOp::Relu: d = a; for (auto &x : d.v) x = std::max(x, 0.0f); break;
            case AjmOp::Tanh: d = a; for (auto &x : d.v) x = std::tanh(x); break;
            case AjmOp::Sigmoid: d = a; for (auto &x : d.v) x = 1.0f / (1.0f + std::exp(-x)); break;
            case AjmOp::Add: d = a; for (size_t n = 0; n < d.v.size(); n++) d.v[n] += t[(size_t)op.in[1]].v[n]; break;
            case AjmOp::Mul: d = a; for (size_t n = 0; n < d.v.size(); n++) d.v[n] *= t[(size_t)op.in[1]].v[n]; break;
            case AjmOp::Concat: {
                int channels = 0;
                for (int s : op.in) channels += t[(size_t)s].c;
                d = Planes(channels, a.w, a.h);
                size_t at = 0;
                for (int s : op.in) { std::copy(t[(size_t)s].v.begin(), t[(size_t)s].v.end(), d.v.begin() + (ptrdiff_t)at); at += t[(size_t)s].v.size(); }
                break;
            }
            }
        }
        const Planes &out = t[(size_t)model_.output];
        require(out.c == 3 && out.w == 2 * w_ && out.h == 2 * h_, "Reference: unexpected output shape");
        for (int y = 0; y < job.crop_h; y++) {
            uint8_t *row = job.out + (ptrdiff_t)y * job.out_stride;
            for (int x = 0; x < job.crop_w; x++)
                for (int k = 0; k < 3; k++) {
                    const float v = out.at(k)[(size_t)(y + job.crop_y) * out.w + x + job.crop_x];
                    row[3 * x + k] = (uint8_t)(std::min(std::max(v, 0.0f), 1.0f) * 255.0f + 0.5f);
                }
        }
    }

private:
    int w_, h_;
    AjmModel model_;
    std::vector<float> weights_;
};

} // namespace

std::unique_ptr<Executor> make_reference_executor(const ExecutorRequest &request)
{
    return std::make_unique<ReferenceExecutor>(request);
}

} // namespace aji
