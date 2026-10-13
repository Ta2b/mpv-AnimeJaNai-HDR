#ifndef AJI_RIFE_FRAME_CACHE_H
#define AJI_RIFE_FRAME_CACHE_H

#include <cstdint>
#include <vector>
#include "net.h"

// Declared before commands and local tensors, so both allocators are returned
// only after those objects have released their buffers, including error paths.
struct AjiRifeWorkspace {
    explicit AjiRifeWorkspace(const ncnn::VulkanDevice* dev) : device(dev),
        blob(dev->acquire_blob_allocator()), staging(dev->acquire_staging_allocator()) {}
    ~AjiRifeWorkspace() {
        device->reclaim_blob_allocator(blob);
        device->reclaim_staging_allocator(staging);
    }
    AjiRifeWorkspace(const AjiRifeWorkspace&) = delete;
    AjiRifeWorkspace& operator=(const AjiRifeWorkspace&) = delete;
    const ncnn::VulkanDevice* device;
    ncnn::VkAllocator *blob, *staging;
};

// Internal RIFE adapter, not part of the bridge ABI. IDs come from the bridge's
// exact RGB comparison; pointers and timestamps are never used as identities.
// Each context is processed serially, and its commands finish before returning.
class AjiRifeFrameCache {
public:
    explicit AjiRifeFrameCache(const ncnn::VulkanDevice* device)
        : device_(device), allocator_(device->acquire_blob_allocator()) {}
    ~AjiRifeFrameCache() {
        // The allocator must remain checked out until every retained tensor dies.
        for (auto& frame : frames_) frame.image.release();
        device_->reclaim_blob_allocator(allocator_);
    }
    AjiRifeFrameCache(const AjiRifeFrameCache&) = delete;
    AjiRifeFrameCache& operator=(const AjiRifeFrameCache&) = delete;

    ncnn::VkMat prepare(const ncnn::Mat& input, uint64_t id, int w, int h,
                        ncnn::VkCompute& cmd, const ncnn::Option& opt,
                        const ncnn::Pipeline* preproc) {
        for (auto& frame : frames_) {
            if (frame.id == id && frame.w == w && frame.h == h) {
                frame.used = ++clock_;
                ++hits;
                return frame.image;
            }
        }
        auto& frame = frames_[frames_[0].used <= frames_[1].used ? 0 : 1];
        frame.id = 0;
        frame.image.release();
        const int pw = (w + 31) / 32 * 32, ph = (h + 31) / 32 * 32;
        frame.image.create(pw, ph, 3, opt.use_fp16_storage ? 2u : 4u, 1, allocator_);
        if (frame.image.empty()) return ncnn::VkMat();

        ncnn::VkMat uploaded;
        cmd.record_clone(input, uploaded, opt);
        if (uploaded.empty()) return ncnn::VkMat();
        // Exactly the original RIFE preprocessing dispatch, including padding,
        // normalization, FP16 storage, RGB order, and intermediate byte rounding.
        std::vector<ncnn::VkMat> bindings{uploaded, frame.image};
        std::vector<ncnn::vk_constant_type> constants(6);
        constants[0].i = uploaded.w;
        constants[1].i = uploaded.h;
        constants[2].i = uploaded.cstep;
        constants[3].i = frame.image.w;
        constants[4].i = frame.image.h;
        constants[5].i = frame.image.cstep;
        cmd.record_pipeline(preproc, bindings, constants, frame.image);
        frame.id = id; frame.w = w; frame.h = h; frame.used = ++clock_;
        ++uploads;
        return frame.image;
    }
    void invalidate() {
        for (auto& frame : frames_) frame.id = 0;
    }
    size_t bytes() const {
        size_t result = 0;
        for (const auto& frame : frames_) result += frame.image.total() * frame.image.elemsize;
        return result;
    }
    uint64_t uploads = 0, hits = 0;

private:
    struct Frame {
        uint64_t id = 0, used = 0;
        int w = 0, h = 0;
        ncnn::VkMat image;
    } frames_[2];
    const ncnn::VulkanDevice* device_;
    ncnn::VkAllocator* allocator_;
    uint64_t clock_ = 0;
};

#endif
