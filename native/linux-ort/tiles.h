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

// Whether a picture is "the same drawing" as another: what decides that a result is reused.
// Compressed video never repeats a held drawing bit for bit: on a web encode at 720p the bytes
// of a held frame differed by 0.6 level on average over their worst 32x32 block and by 7 to 19
// levels at their worst byte, while a frame where something moved has bytes that differ by 34
// levels or more in that sample. These measurements do not cover every movement: a small
// low-contrast change can satisfy both limits and be discarded. Positive thresholds are
// approximate reuse, not a guarantee of unchanged quality (see docs/CHANTIER-PERFORMANCE-RELAIS.md).
// The two limits are:
//   threshold  the largest mean difference of a 32x32 block, in 8-bit levels: catches what
//              changes a little everywhere (a fade, a slow gradient);
//   peak       the largest difference of one byte: catches a small thing that moves, which the
//              mean of its block hides. 0 = no limit on single bytes.
// threshold <= 0 asks for identical bytes.
struct Sameness {
    double threshold = 1.5;
    int peak = 24;
};

// True when no 32x32 block of the window differs from the reference by more than `threshold`
// (mean absolute difference of the block's bytes, in 8-bit levels). `ref` is width * 3 bytes a row.
// and no byte by more than `peak`.
bool window_unchanged(const uint8_t *window, ptrdiff_t stride, const uint8_t *ref, int width, int height, const Sameness &same);

// The same test between two pictures that each have their own row stride.
bool picture_unchanged(const uint8_t *a, ptrdiff_t a_stride, const uint8_t *b, ptrdiff_t b_stride, int width, int height, const Sameness &same);

} // namespace aji
