// Runs a profile through the engine on synthetic frames and prints the timing.
// usage: ort_test CONF MODELS SLOT WIDTH HEIGHT [FRAMES] [DEVICE]
// Environment:
//   AJI_TEST_MOTION   all (default): every frame differs everywhere, nothing can be reused;
//                     none: the same frame every time; corner: only the top-left corner changes;
//                     holds: a new picture every third frame, as a drawing held on screen. The
//                     engine is then told the two frames that follow each one (aji_vk_upcoming)
//   AJI_TEST_FPS      frame rate given to the engine (23.976)
//   AJI_TEST_DUMP     file: the last output frame as raw RGB24
//   AJI_TEST_COMPARE  file: a dump to compare the last frame with (prints the largest and mean
//                     difference); AJI_TEST_TOLERANCE: fail above this largest difference
#include "aji_vulkan.h"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

int main(int argc, char **argv)
{
    if (argc < 6) { std::printf("usage: ort_test CONF MODELS SLOT WIDTH HEIGHT [FRAMES] [DEVICE]\n"); return 2; }
    const int w = std::atoi(argv[4]), h = std::atoi(argv[5]), frames = argc > 6 ? std::atoi(argv[6]) : 10;
    const char *motion_env = std::getenv("AJI_TEST_MOTION");
    const std::string motion = motion_env && *motion_env ? motion_env : "all";
    auto c = aji_vk_create(argv[1], argv[2], "", argc > 7 ? argv[7] : "", "ort-stats.txt", std::atoi(argv[3]));
    if (!c) { std::printf("create failed: %s\n", aji_vk_error(nullptr)); return 1; }
    aji_vk_plan plan;
    const char *fps_env = std::getenv("AJI_TEST_FPS");
    if (aji_vk_configure(c, w, h, fps_env && *fps_env ? std::atof(fps_env) : 23.976, &plan)) { std::printf("configure failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1; }
    std::printf("plan: %dx%d active=%d\n", plan.width, plan.height, plan.active);
    std::vector<unsigned char> in((size_t)w * h * 3), out((size_t)plan.width * plan.height * 3);
    std::vector<unsigned char> ahead[2] = {in, in};
    // A picture with edges and gradients; `shift` moves it. The last frame is always shift 0,
    // so that two runs of the same length end on the same picture whatever the motion.
    auto draw = [&](std::vector<unsigned char> &to, int shift, bool corner_only) {
        for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) for (int k = 0; k < 3; k++) {
            const bool moving = !corner_only || (x < w / 4 && y < h / 4);
            const int s = moving ? shift : 0;
            to[((size_t)y * w + x) * 3 + k] = (unsigned char)(((x + s) * 3 + (y + 2 * s) * 2 + k * 30 + ((x + s) / 16 % 2) * 60) % 256);
        }
    };
    // The picture of frame i: with "holds" it changes every third frame, and the last three
    // frames are the picture of shift 0.
    auto shift_of = [&](int i) { return motion == "none" ? 0 : motion == "holds" ? (frames - 1 - i) / 3 : frames - 1 - i; };
    double total = 0, model = 0, best = 0;
    std::string backend, devices, tiles, placement, boost;
    for (int i = 0; i < frames; i++) {
        draw(in, shift_of(i), motion == "corner");
        if (motion == "holds") {
            const unsigned char *next[2]; ptrdiff_t strides[2]; int count = 0;
            for (int k = 1; k <= 2 && i + k < frames; k++, count++) {
                draw(ahead[count], shift_of(i + k), false);
                next[count] = ahead[count].data(); strides[count] = (ptrdiff_t)w * 3;
            }
            aji_vk_upcoming(c, next, strides, count);
        }
        auto t0 = std::chrono::steady_clock::now();
        if (aji_vk_process(c, nullptr, 0, in.data(), (ptrdiff_t)w * 3, 1.0, out.data(), (ptrdiff_t)plan.width * 3)) {
            std::printf("process failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1;
        }
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (i > 0) total += ms;      // the first frame includes provider compilation
        if (i > 0 && (best == 0 || ms < best)) best = ms;
        if (i == 0) std::printf("first frame: %.1f ms\n", ms);
        // The engine rewrites its statistics at every frame: this frame's time inside the model.
        std::ifstream stats("ort-stats.txt");
        placement.clear();
        for (std::string line; std::getline(stats, line);) {
            if (line.rfind("Backend: ", 0) == 0) backend = line.substr(9);
            if (i > 0 && line.rfind("Model ms: ", 0) == 0) model += std::atof(line.c_str() + 10);
            if (line.rfind("Devices:", 0) == 0) devices = line;
            if (line.rfind("Tiles:", 0) == 0) tiles = line;
            if (line.rfind("Placement:", 0) == 0) placement += line + "\n";
            if (line.rfind("Boost:", 0) == 0) boost = line;
        }
    }
    auto bounds = std::minmax_element(out.begin(), out.end());
    std::printf("average after the first frame: %.1f ms | output range %d..%d | centre pixel %d %d %d\n",
                frames > 1 ? total / (frames - 1) : 0.0, *bounds.first, *bounds.second,
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3],
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3 + 1],
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3 + 2]);
    if (frames > 1) {
        const double frame = total / (frames - 1), inside = model / (frames - 1);
        // One line per run, easy to collect: everything after the first frame.
        std::printf("RESULT | %s | %dx%d -> %dx%d | frame %.1f ms (best %.1f) | model %.1f ms | conversions %.1f ms | %.1f fps\n",
                    backend.c_str(), w, h, plan.width, plan.height, frame, best, inside, frame - inside, 1000.0 / frame);
    }
    if (!tiles.empty()) std::printf("%s\n", tiles.c_str());
    if (!devices.empty()) std::printf("%s\n", devices.c_str());
    if (!placement.empty()) std::printf("%s", placement.c_str());
    if (!boost.empty()) std::printf("%s\n", boost.c_str());
    int status = *bounds.first == *bounds.second ? 1 : 0;
    if (const char *dump = std::getenv("AJI_TEST_DUMP"); dump && *dump)
        std::ofstream(dump, std::ios::binary).write((const char *)out.data(), (std::streamsize)out.size());
    if (const char *path = std::getenv("AJI_TEST_COMPARE"); path && *path) {
        std::ifstream file(path, std::ios::binary);
        std::vector<unsigned char> ref((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        if (ref.size() != out.size()) { std::printf("COMPARE failed: %zu bytes against %zu\n", out.size(), ref.size()); status = 1; }
        else {
            int worst = 0; double sum = 0; size_t differing = 0;
            for (size_t i = 0; i < out.size(); i++) {
                const int d = std::abs((int)out[i] - (int)ref[i]);
                worst = std::max(worst, d); sum += d; differing += d != 0;
            }
            std::printf("COMPARE | largest difference %d | mean %.4f | values differing %zu of %zu\n", worst, sum / out.size(), differing, out.size());
            const char *tolerance = std::getenv("AJI_TEST_TOLERANCE");
            if (tolerance && *tolerance && worst > std::atoi(tolerance)) { std::printf("COMPARE failed: above the tolerance of %s\n", tolerance); status = 1; }
        }
    }
    aji_vk_destroy(c);
    return status;
}
