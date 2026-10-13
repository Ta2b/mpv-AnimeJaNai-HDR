// Cutting a model input in tiles, and telling whether a tile changed since it was computed.
// Plain functions, used by the core and exercised alone by tiles_test.cpp.
#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace aji {

struct Tile {
    int x0 = 0, y0 = 0, x1 = 0, y1 = 0;   // the part of the input this tile owns
    int wx = 0, wy = 0;                    // top-left of its window (every window has the plan's size)
};

struct TilePlan {
    int width = 0, height = 0;   // window size
    int nx = 1, ny = 1;
    std::vector<Tile> tiles;
};

// Cuts w x h (even) in nx x ny tiles whose windows all have one size. A window holds its tile
// plus `reach` pixels past every edge that is not an edge of the frame, so that a convolutional
// model gives the tile the pixels it would give it in the whole frame. The grid is reduced when
// the tiles would be smaller than their overlap. `align`: the window width is rounded up to a
// multiple of it when the frame is wide enough (an executor may need it, see the core).
// `min_window`: the smallest window side an executor takes (a Core ML template: 256); the grid
// is reduced along an axis until its windows reach it. The frame itself is at least that large.
TilePlan plan_tiles(int w, int h, int nx, int ny, int reach, int align = 2, int min_window = 0);

// "auto", "1", "off", "2x2", "3x2"...: the grid a frame is cut in when all of it is computed,
// for `executors` devices. Auto keeps one tile for one device.
void grid_for(const char *setting, int executors, int w, int h, int *nx, int *ny);

// "auto", "off", "4x3"...: the finer grid used when only a part of the frame changed. Auto aims
// at areas of about 320x240 pixels: small enough to follow a mouth or a blink, large enough for
// the overlap around each one to stay a fraction of it.
void areas_for(const char *setting, int w, int h, int *nx, int *ny);

// True when no 32x32 block of the window differs from the reference by more than `threshold`
// (mean absolute difference of the block's bytes, in 8-bit levels). `ref` is width * 3 bytes a row.
bool window_unchanged(const uint8_t *window, ptrdiff_t stride, const uint8_t *ref, int width, int height, double threshold);

} // namespace aji
