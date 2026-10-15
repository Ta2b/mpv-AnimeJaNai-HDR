// Optional immutable RGB24 source identities; pointers never identify content.
#pragma once
#include <cstdint>
#include <cstddef>
namespace aji {
struct SourceKey {
    uint64_t generation = 0, sequence = 0;
    int width = 0, height = 0;
    ptrdiff_t stride = 0;
    bool valid() const { return generation && sequence && width > 0 && height > 0 && stride; }
    bool matches(const SourceKey &other) const {
        return valid() && other.valid() && generation == other.generation && sequence == other.sequence &&
               width == other.width && height == other.height && stride == other.stride;
    }
};
struct SourceIds {
    uint64_t generation = 0, previous = 0, current = 0;
    SourceKey key(bool left, int width, int height, ptrdiff_t stride) const {
        return {generation, left ? previous : current, width, height, stride};
    }
};
// A recycled counter disables trusted IDs until a fresh, higher generation.
// This fails closed even for a client that forgets the generation at seek.
struct SourceIdTracker {
    uint64_t generation = 0, maximum = 0, rejected_calls = 0;
    bool invalid = false;
    SourceIds accept(uint64_t epoch, uint64_t left, uint64_t right) {
        if (!epoch || !right) return {};
        if (epoch < generation) { ++rejected_calls; return {}; }
        if (epoch > generation) { generation = epoch; maximum = 0; invalid = false; }
        if (invalid || right < maximum || left > right) {
            invalid = true; ++rejected_calls; return {};
        }
        maximum = right;
        return {epoch, left, right};
    }
};
} // namespace aji
