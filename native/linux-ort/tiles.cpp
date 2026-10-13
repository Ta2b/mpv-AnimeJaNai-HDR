#include "tiles.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <string>

namespace aji {
namespace {

// Even boundaries of n parts of `size`, and the common window length along that axis.
void cut(int size, int n, int reach, int align, std::vector<int> *edges, int *window)
{
    // A tile must be longer than what its neighbours read from it, or the windows of the two
    // ends would be the whole frame anyway.
    while (n > 1 && size / n < std::max(2 * reach, 32)) n--;
    edges->assign((size_t)n + 1, 0);
    for (int i = 1; i < n; i++) (*edges)[(size_t)i] = (int)((long long)size * i / n) / 2 * 2;
    (*edges)[(size_t)n] = size;
    int need = size;
    if (n > 1) {
        need = 0;
        for (int i = 0; i < n; i++) {
            const int own = (*edges)[(size_t)i + 1] - (*edges)[(size_t)i];
            need = std::max(need, own + (i > 0 ? reach : 0) + (i + 1 < n ? reach : 0));
        }
        need = (need + 1) / 2 * 2;
        if (align > 2) need = (need + align - 1) / align * align;
        need = std::min(size, need);
    }
    *window = need;
}

} // namespace

TilePlan plan_tiles(int w, int h, int nx, int ny, int reach, int align)
{
    reach = std::max(0, (reach + 1) / 2 * 2);
    std::vector<int> xs, ys;
    TilePlan plan;
    cut(w, std::max(1, nx), reach, align, &xs, &plan.width);
    cut(h, std::max(1, ny), reach, 2, &ys, &plan.height);
    plan.nx = (int)xs.size() - 1;
    plan.ny = (int)ys.size() - 1;
    for (int j = 0; j < plan.ny; j++) {
        for (int i = 0; i < plan.nx; i++) {
            Tile t;
            t.x0 = xs[(size_t)i]; t.x1 = xs[(size_t)i + 1];
            t.y0 = ys[(size_t)j]; t.y1 = ys[(size_t)j + 1];
            // As far left / up as the overlap asks, but never past the far edge of the frame.
            t.wx = std::max(0, std::min(t.x0 - (i > 0 ? reach : 0), w - plan.width));
            t.wy = std::max(0, std::min(t.y0 - (j > 0 ? reach : 0), h - plan.height));
            plan.tiles.push_back(t);
        }
    }
    return plan;
}

void grid_for(const char *setting, int executors, bool reuse_tiles, int w, int h, int *nx, int *ny)
{
    const std::string s = setting ? setting : "";
    *nx = *ny = 1;
    if (s == "1" || s == "off" || s == "no") return;
    const size_t by = s.find('x');
    if (by != std::string::npos) {
        *nx = std::max(1, std::min(8, std::atoi(s.substr(0, by).c_str())));
        *ny = std::max(1, std::min(8, std::atoi(s.substr(by + 1).c_str())));
        return;
    }
    if (executors <= 1 && !reuse_tiles) return;
    // Four tiles for two devices: the faster one takes three while the slower takes one. More
    // devices get two tiles each. Wide columns rather than rows: frames are wider than tall.
    const int wanted = std::max(4, 2 * executors);
    *ny = 2;
    *nx = (wanted + 1) / 2;
    if (w < 2 * h / 3) std::swap(*nx, *ny);   // portrait
}

bool window_unchanged(const uint8_t *window, ptrdiff_t stride, const uint8_t *ref, int width, int height, double threshold)
{
    const int block = 32;
    const int columns = (width + block - 1) / block;
    std::vector<uint32_t> sums((size_t)columns);
    if (threshold <= 0) {
        for (int y = 0; y < height; y++)
            if (std::memcmp(window + (ptrdiff_t)y * stride, ref + (size_t)y * width * 3, (size_t)width * 3) != 0) return false;
        return true;
    }
    for (int top = 0; top < height; top += block) {
        const int rows = std::min(block, height - top);
        std::fill(sums.begin(), sums.end(), 0u);
        for (int y = top; y < top + rows; y++) {
            const uint8_t *a = window + (ptrdiff_t)y * stride, *b = ref + (size_t)y * width * 3;
            for (int c = 0; c < columns; c++) {
                const int first = c * block * 3, last = std::min(width, (c + 1) * block) * 3;
                uint32_t sum = 0;
                for (int k = first; k < last; k++) sum += (uint32_t)std::abs((int)a[k] - (int)b[k]);
                sums[(size_t)c] += sum;
            }
        }
        for (int c = 0; c < columns; c++) {
            const int pixels = (std::min(width, (c + 1) * block) - c * block) * rows;
            if ((double)sums[(size_t)c] > threshold * pixels * 3) return false;
        }
    }
    return true;
}

} // namespace aji
