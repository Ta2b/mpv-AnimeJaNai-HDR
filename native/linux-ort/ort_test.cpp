// Runs a profile through the engine on synthetic frames and prints the timing.
// usage: ort_test CONF MODELS SLOT WIDTH HEIGHT [FRAMES] [DEVICE]
// Environment:
//   AJI_TEST_MOTION   all (default): every frame differs everywhere, nothing can be reused;
//                     none: the same frame every time; corner: only the top-left corner changes;
//                     holds: a new picture every third frame, as a drawing held on screen. The
//                     engine is then told the two frames that follow each one (aji_vk_upcoming)
//   AJI_TEST_FPS      frame rate given to the engine (23.976)
//   AJI_TEST_WARMUP   number of initial source frames excluded (default 1)
//   AJI_RIFE_PROFILE  1: report preparation, inference and output separately
//   AJI_TEST_RIFE_DIR folder of the RIFE models (default: MODELS). With a profile that
//                     interpolates, every frame after the first is asked for as the player does:
//                     the pictures between it and the previous one, then the frame itself.
//   AJI_TEST_TRIO     prefix: the last pair as raw RGB24, PREFIX-a.rgb, PREFIX-between.rgb (the
//                     first picture between them) and PREFIX-b.rgb
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
    const char *rife_dir = std::getenv("AJI_TEST_RIFE_DIR");
    auto c = aji_vk_create(argv[1], argv[2], rife_dir && *rife_dir ? rife_dir : argv[2], argc > 7 ? argv[7] : "", "ort-stats.txt", std::atoi(argv[3]));
    if (!c) { std::printf("create failed: %s\n", aji_vk_error(nullptr)); return 1; }
    aji_vk_plan plan;
    const char *fps_env = std::getenv("AJI_TEST_FPS");
    if (aji_vk_configure(c, w, h, fps_env && *fps_env ? std::atof(fps_env) : 23.976, &plan)) { std::printf("configure failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1; }
    std::printf("plan: %dx%d active=%d", plan.width, plan.height, plan.active);
    if (plan.numerator != plan.denominator) std::printf(" interpolation=%d/%d", plan.numerator, plan.denominator);
    std::printf("\n");
    std::vector<unsigned char> in((size_t)w * h * 3), out((size_t)plan.width * plan.height * 3);
    std::vector<unsigned char> before, first_out, between_out, trio[3];
    const bool interpolating = plan.numerator > plan.denominator;
    const char *trio_prefix = std::getenv("AJI_TEST_TRIO");
    const bool keep_trio = trio_prefix && *trio_prefix;
    const char *warmup_env = std::getenv("AJI_TEST_WARMUP");
    const int warmup = std::max(1, std::min(std::max(1, frames - 1), warmup_env ? std::atoi(warmup_env) : 1));
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
    double previous_model = 0, previous_prepare = 0, previous_infer = 0, previous_output = 0, previous_wait = 0;
    double prepare = 0, infer = 0, output_time = 0, overlap_wait = 0;
    std::vector<double> samples;
    std::string rife_profile;
    std::string backend, devices, tiles, placement, boost, rife;
    for (int i = 0; i < frames; i++) {
        if (interpolating) before = in;
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
        // As the player's filter does: the instants between the previous frame and this one.
        if (interpolating && i > 0) {
            if (keep_trio) first_out = out;
            int pictures = 0;
            for (int acc = plan.denominator; acc < plan.numerator; acc += plan.denominator, pictures++) {
                if (aji_vk_process(c, before.data(), (ptrdiff_t)w * 3, in.data(), (ptrdiff_t)w * 3, (double)acc / plan.numerator,
                                   out.data(), (ptrdiff_t)plan.width * 3)) {
                    std::printf("process failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1;
                }
                if (keep_trio && pictures == 0) between_out = out;
            }
        }
        if (aji_vk_process(c, interpolating && i > 0 ? before.data() : nullptr, (ptrdiff_t)w * 3, in.data(), (ptrdiff_t)w * 3, 1.0,
                           out.data(), (ptrdiff_t)plan.width * 3)) {
            std::printf("process failed: %s\n", aji_vk_error(c)); aji_vk_destroy(c); return 1;
        }
        if (keep_trio && interpolating && i > 0) { trio[0] = first_out; trio[1] = between_out; trio[2] = out; }
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (i >= warmup) { total += ms; samples.push_back(ms); }
        if (i >= warmup && (best == 0 || ms < best)) best = ms;
        if (i == 0) std::printf("first frame: %.1f ms\n", ms);
        // A source interval can contain several calls. Read cumulative work, not only the
        // final endpoint call (which is cached when RIFE precomputed it).
        std::ifstream stats("ort-stats.txt");
        placement.clear();
        double current_model = 0, average_model = 0, current_prepare = 0, current_infer = 0, current_output = 0, current_wait = 0;
        uint64_t calls = 0;
        bool model_total_available = false;
        for (std::string line; std::getline(stats, line);) {
            if (line.rfind("Backend: ", 0) == 0) backend = line.substr(9);
            auto value = [&](const char *key, double &to) {
                const std::string prefix = std::string(key) + ": ";
                if (line.rfind(prefix, 0) != 0) return false;
                to = std::atof(line.c_str() + prefix.size()); return true;
            };
            if (value("Model total ms", current_model)) model_total_available = true;
            value("Average model ms", average_model);
            if (line.rfind("Frames: ", 0) == 0) calls = std::strtoull(line.c_str() + 8, nullptr, 10);
            value("RIFE preparation total ms", current_prepare);
            value("RIFE inference total ms", current_infer);
            value("RIFE output total ms", current_output);
            value("RIFE overlap wait total ms", current_wait);
            if (line.rfind("RIFE profiling: ", 0) == 0) rife_profile = line.substr(16);
            if (line.rfind("Devices:", 0) == 0) devices = line;
            if (line.rfind("Tiles:", 0) == 0) tiles = line;
            if (line.rfind("Placement:", 0) == 0) placement += line + "\n";
            if (line.rfind("Boost:", 0) == 0) boost = line;
            if (line.rfind("RIFE:", 0) == 0) rife = line;
        }
        if (!model_total_available) current_model = average_model * calls; // older libraries
        if (i >= warmup) {
            model += current_model - previous_model;
            prepare += current_prepare - previous_prepare;
            infer += current_infer - previous_infer;
            output_time += current_output - previous_output;
            overlap_wait += current_wait - previous_wait;
        }
        previous_model = current_model; previous_prepare = current_prepare; previous_infer = current_infer;
        previous_output = current_output; previous_wait = current_wait;
    }
    auto bounds = std::minmax_element(out.begin(), out.end());
    std::printf("average after warmup (%d source frames): %.1f ms | output range %d..%d | centre pixel %d %d %d\n",
                warmup, !samples.empty() ? total / samples.size() : 0.0, *bounds.first, *bounds.second,
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3],
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3 + 1],
                out[((size_t)(plan.height / 2) * plan.width + plan.width / 2) * 3 + 2]);
    if (!samples.empty()) {
        const double frame = total / samples.size(), inside = model / samples.size();
        std::printf("RESULT | %s | %dx%d -> %dx%d | frame %.1f ms (best %.1f) | upscale work %.1f ms | other %.1f ms | %.1f fps\n",
                    backend.c_str(), w, h, plan.width, plan.height, frame, best, inside, frame - inside, 1000.0 / frame);
        std::sort(samples.begin(), samples.end());
        const size_t middle = samples.size() / 2;
        const double median = samples.size() % 2 ? samples[middle] : (samples[middle-1] + samples[middle]) / 2;
        const size_t p95 = (95 * samples.size() + 99) / 100 - 1;
        std::printf("SPREAD | %zu source intervals | warmup %d | median %.1f ms | p95 %.1f ms | max %.1f ms\n",
                    samples.size(), warmup, median, samples[p95], samples.back());
        if (median > 0 && samples.back() > 3 * median)
            std::printf("MEASUREMENT | large stalls observed: repeat with session unlocked; this run does not identify their cause\n");
        if (rife_profile == "on")
            std::printf("TIMING | per source | RIFE prep %.3f ms | inference %.3f ms | output %.3f ms | overlap wait %.3f ms | workloads can overlap\n",
                        prepare / samples.size(), infer / samples.size(), output_time / samples.size(), overlap_wait / samples.size());
    }
    if (!tiles.empty()) std::printf("%s\n", tiles.c_str());
    if (!devices.empty()) std::printf("%s\n", devices.c_str());
    if (!placement.empty()) std::printf("%s", placement.c_str());
    if (!boost.empty()) std::printf("%s\n", boost.c_str());
    if (!rife.empty() && rife != "RIFE: off") std::printf("%s\n", rife.c_str());
    if (keep_trio && !trio[0].empty()) {
        const char *names[3] = {"-a.rgb", "-between.rgb", "-b.rgb"};
        for (int k = 0; k < 3; k++)
            std::ofstream(std::string(trio_prefix) + names[k], std::ios::binary).write((const char *)trio[k].data(), (std::streamsize)trio[k].size());
    }
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
