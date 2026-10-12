// Runs a profile through the ONNX Runtime engine on a synthetic frame and prints the timing.
// usage: ort_test CONF MODELS SLOT WIDTH HEIGHT [FRAMES] [DEVICE]
#include "aji_vulkan.h"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

int main(int argc, char **argv)
{
    if (argc < 6) { std::printf("usage: ort_test CONF MODELS SLOT WIDTH HEIGHT [FRAMES] [DEVICE]\n"); return 2; }
    const int w = std::atoi(argv[4]), h = std::atoi(argv[5]), frames = argc > 6 ? std::atoi(argv[6]) : 10;
    auto c = aji_vk_create(argv[1], argv[2], "", argc > 7 ? argv[7] : "", "ort-stats.txt", std::atoi(argv[3]));
    if (!c) { std::printf("create failed: %s\n", aji_vk_error(nullptr)); return 1; }
    aji_vk_plan plan;
    if (aji_vk_configure(c, w, h, 23.976, &plan)) { std::printf("configure failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1; }
    std::printf("plan: %dx%d active=%d\n", plan.width, plan.height, plan.active);
    std::vector<unsigned char> in((size_t)w * h * 3), out((size_t)plan.width * plan.height * 3);
    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) for (int k = 0; k < 3; k++)
        in[((size_t)y * w + x) * 3 + k] = (unsigned char)((x * 3 + y * 2 + k * 30) % 256);
    double total = 0;
    for (int i = 0; i < frames; i++) {
        auto t0 = std::chrono::steady_clock::now();
        if (aji_vk_process(c, nullptr, 0, in.data(), (ptrdiff_t)w * 3, 1.0, out.data(), (ptrdiff_t)plan.width * 3)) {
            std::printf("process failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1;
        }
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (i > 0) total += ms;      // the first frame includes provider compilation
        if (i == 0) std::printf("first frame: %.1f ms\n", ms);
    }
    auto bounds = std::minmax_element(out.begin(), out.end());
    std::printf("average after the first frame: %.1f ms | output range %d..%d | centre pixel %d %d %d\n",
                frames > 1 ? total / (frames - 1) : 0.0, *bounds.first, *bounds.second,
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3],
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3 + 1],
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3 + 2]);
    {
        std::ifstream stats("ort-stats.txt");
        for (std::string line; std::getline(stats, line);)
            if (line.rfind("Average model ms", 0) == 0 || line.rfind("Average conversion ms", 0) == 0)
                std::printf("%s (first frame included)\n", line.c_str());
    }
    aji_vk_destroy(c);
    return *bounds.first == *bounds.second ? 1 : 0;
}
