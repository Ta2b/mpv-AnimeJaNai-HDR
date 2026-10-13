// Checks of the pieces that need no model: the tile plans, the "unchanged" test and the Core ML
// size patch. usage: tiles_test [MODELS_DIR MODEL CHECK_PACKAGE HEIGHT WIDTH]
// With the arguments, the package written for HEIGHT x WIDTH must be byte for byte the one
// coremltools made for that size (CHECK_PACKAGE, kept by convert_models.py --keep-check).
#include "ajm.h"
#include "mlpatch.h"
#include "tiles.h"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

static int failures = 0;
static void check(bool ok, const std::string &what)
{
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", what.c_str());
    if (!ok) failures++;
}

static std::vector<char> bytes(const std::filesystem::path &p)
{
    std::ifstream f(p, std::ios::binary);
    return std::vector<char>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}

int main(int argc, char **argv)
{
    using namespace aji;
    // Every pixel belongs to exactly one tile; every window is inside the frame, has the plan's
    // size and holds its tile with the overlap on the inner edges.
    const int sizes[][2] = {{1280, 720}, {1920, 1080}, {960, 540}, {1720, 720}, {640, 360}, {256, 256}, {3840, 2160}, {722, 404}};
    const int grids[][2] = {{1, 1}, {2, 2}, {3, 2}, {2, 1}, {4, 3}};
    bool cover = true, inside = true, margins = true, even = true;
    for (auto &s : sizes) for (auto &g : grids) for (int reach : {0, 36, 54}) for (int align : {2, 32}) {
        const int w = s[0], h = s[1];
        const TilePlan plan = plan_tiles(w, h, g[0], g[1], reach, align);
        std::vector<char> owner((size_t)w * h, 0);
        even = even && plan.width % 2 == 0 && plan.height % 2 == 0;
        for (size_t k = 0; k < plan.tiles.size(); k++) {
            const Tile &t = plan.tiles[k];
            const int i = (int)k % plan.nx, j = (int)k / plan.nx;
            inside = inside && t.wx >= 0 && t.wy >= 0 && t.wx + plan.width <= w && t.wy + plan.height <= h
                && t.x0 >= t.wx && t.x1 <= t.wx + plan.width && t.y0 >= t.wy && t.y1 <= t.wy + plan.height;
            margins = margins && (i == 0 || t.x0 - t.wx >= reach) && (i == plan.nx - 1 || t.wx + plan.width - t.x1 >= reach)
                && (j == 0 || t.y0 - t.wy >= reach) && (j == plan.ny - 1 || t.wy + plan.height - t.y1 >= reach);
            even = even && t.x0 % 2 == 0 && t.y0 % 2 == 0 && t.wx % 2 == 0 && t.wy % 2 == 0;
            for (int y = t.y0; y < t.y1; y++) for (int x = t.x0; x < t.x1; x++) owner[(size_t)y * w + x]++;
        }
        for (char n : owner) cover = cover && n == 1;
    }
    check(cover, "every pixel belongs to exactly one tile");
    check(inside, "every window is inside the frame and holds its tile");
    check(margins, "inner edges have the overlap the model needs");
    check(even, "tiles and windows start on even pixels and have even sizes");
    {
        const TilePlan one = plan_tiles(1280, 720, 1, 1, 36);
        check(one.tiles.size() == 1 && one.width == 1280 && one.height == 720, "one tile is the whole frame");
        const TilePlan four = plan_tiles(1280, 720, 2, 2, 36);
        check(four.tiles.size() == 4 && four.width == 676 && four.height == 396, "2x2 of 720p: windows of 676x396 with an overlap of 36");
        const TilePlan aligned = plan_tiles(1280, 720, 2, 2, 36, 32);
        check(aligned.tiles.size() == 4 && aligned.width == 704 && aligned.height == 396 && aligned.tiles[1].wx == 576,
              "aligned windows: 704 wide, the right ones start at 576");
        // A Core ML template takes no window under 256 pixels a side: 640x360 in 2x2 would have
        // windows 216 pixels high, so the rows are merged; 1280x720 keeps its four tiles.
        const TilePlan low = plan_tiles(640, 360, 2, 2, 36, 2, 256);
        check(low.nx == 2 && low.ny == 1 && low.width == 356 && low.height == 360, "a grid is reduced until its windows reach the executor's minimum");
        const TilePlan tiny = plan_tiles(256, 256, 3, 2, 36, 2, 256);
        check(tiny.tiles.size() == 1 && tiny.width == 256 && tiny.height == 256, "a frame of the minimum size is one tile");
        const TilePlan kept = plan_tiles(1280, 720, 2, 2, 36, 2, 256);
        check(kept.tiles.size() == 4 && kept.width == four.width && kept.height == four.height, "the minimum changes nothing when windows are larger");
        const TilePlan twelve = plan_tiles(1280, 720, 4, 3, 36, 2, 256);
        check(twelve.nx == 4 && twelve.ny == 3 && twelve.width == 392 && twelve.height == 312, "4x3 of 720p stays: with their overlap the windows are 392x312");
        const TilePlan small = plan_tiles(128, 96, 2, 2, 36);
        check(small.tiles.size() == 1, "tiles smaller than their overlap are not cut");
        int nx, ny;
        grid_for("auto", 1, false, 1280, 720, &nx, &ny); check(nx == 1 && ny == 1, "auto: one device, one tile");
        grid_for("auto", 2, false, 1280, 720, &nx, &ny); check(nx == 2 && ny == 2, "auto: two devices share four tiles");
        grid_for("auto", 1, true, 1280, 720, &nx, &ny); check(nx == 2 && ny == 2, "auto: partial reuse cuts in four");
        grid_for("3x2", 1, false, 1280, 720, &nx, &ny); check(nx == 3 && ny == 2, "explicit grid");
        grid_for("1", 2, true, 1280, 720, &nx, &ny); check(nx == 1 && ny == 1, "tiles off");
    }
    {
        const int w = 200, h = 100;
        std::vector<uint8_t> a((size_t)w * h * 3), b;
        for (size_t i = 0; i < a.size(); i++) a[i] = (uint8_t)(i * 7 % 251);
        b = a;
        check(window_unchanged(a.data(), w * 3, b.data(), w, h, 0.4), "identical windows are unchanged");
        check(window_unchanged(a.data(), w * 3, b.data(), w, h, 0), "threshold 0 accepts identical windows");
        b[1234] ^= 1;
        check(!window_unchanged(a.data(), w * 3, b.data(), w, h, 0), "threshold 0 rejects one changed value");
        check(window_unchanged(a.data(), w * 3, b.data(), w, h, 0.4), "one value off by one is noise");
        b = a;
        for (int y = 40; y < 48; y++) for (int x = 150; x < 158; x++) for (int k = 0; k < 3; k++) b[((size_t)y * w + x) * 3 + k] = (uint8_t)(a[((size_t)y * w + x) * 3 + k] + 60);
        check(!window_unchanged(a.data(), w * 3, b.data(), w, h, 0.4), "a small object that moved changes its block");
        b = a;
        for (auto &v : b) v = (uint8_t)std::min(255, v + 1);
        check(!window_unchanged(a.data(), w * 3, b.data(), w, h, 0.4), "a fade of one level everywhere is a change");
        // Rows of the window are `stride` apart in a larger picture.
        std::vector<uint8_t> big((size_t)(w + 50) * h * 3, 9);
        for (int y = 0; y < h; y++) std::memcpy(big.data() + (size_t)y * (w + 50) * 3 + 30, a.data() + (size_t)y * w * 3, (size_t)w * 3);
        check(window_unchanged(big.data() + 30, (w + 50) * 3, a.data(), w, h, 0.4), "a window inside a larger frame");
    }
    if (argc >= 6) {
        const std::string models = argv[1], model = argv[2];
        const std::filesystem::path expected = argv[3];
        const int h = std::atoi(argv[4]), w = std::atoi(argv[5]);
        const AjmModel description = load_ajm(models + "/" + model + ".ajm");
        std::printf("model reach: %d pixels, %zu operations\n", description.reach(), description.ops.size());
        check(description.reach() >= 8 && description.reach() <= 128, "the model description gives a plausible reach");
        const std::filesystem::path made = std::filesystem::temp_directory_path() / "aji-mlpatch-test.mlpackage";
        bool same = false;
        try {
            write_coreml_package(models, model, w, h, made.string());
            const char *spec = "Data/com.apple.CoreML/model.mlmodel", *blob = "Data/com.apple.CoreML/weights/weight.bin";
            same = bytes(made / spec) == bytes(expected / spec) && !bytes(made / spec).empty()
                && bytes(made / blob) == bytes(expected / blob) && std::filesystem::exists(made / "Manifest.json");
        } catch (const std::exception &e) { std::printf("error: %s\n", e.what()); }
        check(same, "the Core ML package made for " + std::to_string(w) + "x" + std::to_string(h) + " is the one coremltools makes");
        bool refused = false;
        try { write_coreml_package(models, model, 200, 720, made.string()); } catch (const std::exception &) { refused = true; }
        check(refused, "a size the template cannot express is refused");
        check(coreml_template_tag(models, model).size() == 12, "the template has a cache tag");
        std::error_code ignored;
        std::filesystem::remove_all(made, ignored);
    }
    std::printf("%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
