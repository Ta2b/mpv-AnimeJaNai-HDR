// Experimental decode/import consumer, explicitly separate from inference.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <CoreVideo/CoreVideo.h>
#include "nv12_import_probe.h"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>

namespace {
void message(char *out,uint32_t capacity,const char *value) {if(out&&capacity)std::snprintf(out,capacity,"%s",value);}
void require(bool ok,const char *why){if(!ok)throw std::runtime_error(why);}
struct Unsupported : std::runtime_error {using std::runtime_error::runtime_error;};
struct Counters {
    std::atomic<uint64_t> imports{0},live{0},peak{0},sampled{0},validation{0},resets{0};
};
struct Imported {
    std::shared_ptr<Counters> counters;
    CVPixelBufferRef buffer=nullptr;
    CVMetalTextureCacheRef cache=nullptr;
    CVMetalTextureRef views[2]={nullptr,nullptr};
    __strong id<MTLTexture> textures[2]={nil,nil};
    explicit Imported(std::shared_ptr<Counters> c):counters(std::move(c)) {
        uint64_t live=++counters->live,peak=counters->peak.load();
        while(peak<live&&!counters->peak.compare_exchange_weak(peak,live)){}
    }
    ~Imported(){for(auto view:views)if(view)CFRelease(view);if(buffer)CVPixelBufferRelease(buffer);if(cache)CFRelease(cache);--counters->live;}
};
struct Context {
    __strong id<MTLDevice> device=nil;
    __strong id<MTLCommandQueue> queue=nil;
    __strong id<MTLBuffer> samples[2]={nil,nil};
    CVMetalTextureCacheRef cache=nullptr;
    std::shared_ptr<Counters> counters=std::make_shared<Counters>();
    ~Context(){if(cache){CVMetalTextureCacheFlush(cache,0);CFRelease(cache);}}
};
int query(void *handle,void *pixel,const aji_apple_nv12_view_v1 *v,char *reason,uint32_t capacity)
{
    const char *why=nullptr;auto *c=static_cast<Context *>(handle);auto buffer=(CVPixelBufferRef)pixel;
    if(!c||!v||v->size<sizeof(*v)||v->version!=1||!buffer)why="invalid Apple NV12 probe view";
    else if(v->flags!=AJI_APPLE_NV12_SDR709)why="only declared SDR BT.709 is imported; software fallback preserves source metadata";
    else if(v->rotation||v->crop_x0>=v->crop_x1||v->crop_y0>=v->crop_y1||v->crop_x1>v->width||v->crop_y1>v->height||
            !v->width||!v->height||v->width>16384||v->height>16384||((v->width|v->height|v->crop_x0|v->crop_y0|v->crop_x1|v->crop_y1)&1))
        why="unsupported NV12 crop, rotation or chroma geometry";
    else if(CVPixelBufferGetPixelFormatType(buffer)!=kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)
        why="only 8-bit video-range NV12 (420v) is imported; no implicit P010/HDR truncation";
    else if(!CVPixelBufferIsPlanar(buffer)||CVPixelBufferGetPlaneCount(buffer)!=2||
            CVPixelBufferGetWidth(buffer)!=v->width||CVPixelBufferGetHeight(buffer)!=v->height||
            CVPixelBufferGetWidthOfPlane(buffer,0)!=v->width||CVPixelBufferGetHeightOfPlane(buffer,0)!=v->height||
            CVPixelBufferGetWidthOfPlane(buffer,1)!=v->width/2||CVPixelBufferGetHeightOfPlane(buffer,1)!=v->height/2)
        why="NV12 plane dimensions differ from the declared view";
    else if(!CVPixelBufferGetIOSurface(buffer))why="CVPixelBuffer has no IOSurface for Metal import";
    if(why){message(reason,capacity,why);return 1;}
    message(reason,capacity,"");return 0;
}
void *create(char *error,uint32_t capacity) {
    @autoreleasepool { @try {try {
        auto c=std::make_unique<Context>();c->device=MTLCreateSystemDefaultDevice();require(c->device!=nil,"no Metal device for NV12 import");
        c->queue=[c->device newCommandQueue];require(c->queue!=nil,"cannot create Metal import consumer queue");
        require(CVMetalTextureCacheCreate(kCFAllocatorDefault,nullptr,c->device,nullptr,&c->cache)==kCVReturnSuccess,
            "cannot create CVMetalTextureCache on the consumer device");
        for(auto &sample:c->samples) {
            sample=[c->device newBufferWithLength:256 options:MTLResourceStorageModeShared];
            require(sample!=nil,"cannot allocate fixed import sample buffers");
        }
        message(error,capacity,"");return c.release();
    }catch(const std::exception &e){message(error,capacity,e.what());return nullptr;}} @catch(NSException *e){message(error,capacity,(e.reason?e.reason.UTF8String:"Metal import exception"));return nullptr;} }
}
int consume(void *handle,void *pixel,const aji_apple_nv12_view_v1 *v,const aji_apple_nv12_readback_v1 *readback,char *error,uint32_t capacity) {
    @autoreleasepool { @try {try {
        if(query(handle,pixel,v,error,capacity))return 1;
        auto &c=*static_cast<Context *>(handle);auto owner=std::make_shared<Imported>(c.counters);owner->buffer=CVPixelBufferRetain((CVPixelBufferRef)pixel);
        owner->cache=(CVMetalTextureCacheRef)CFRetain(c.cache);
        for(size_t plane=0;plane<2;++plane) {
            const size_t w=CVPixelBufferGetWidthOfPlane(owner->buffer,plane),h=CVPixelBufferGetHeightOfPlane(owner->buffer,plane);
            if(CVMetalTextureCacheCreateTextureFromImage(kCFAllocatorDefault,c.cache,owner->buffer,nullptr,
                plane?MTLPixelFormatRG8Unorm:MTLPixelFormatR8Unorm,w,h,plane,&owner->views[plane])!=kCVReturnSuccess)
                throw Unsupported("CoreVideo could not import the NV12 plane on the consumer Metal device");
            owner->textures[plane]=CVMetalTextureGetTexture(owner->views[plane]);
            require(owner->textures[plane]!=nil&&owner->textures[plane].device.registryID==c.device.registryID,"NV12 texture device mismatch");
        }
        if(readback) {
            require(readback->size>=sizeof(*readback)&&readback->y&&readback->uv,"invalid validation destinations");
            require(readback->y_stride>=v->width&&readback->uv_stride>=v->width&&
                readback->y_stride<=UINT64_MAX/v->height&&readback->uv_stride<=UINT64_MAX/(v->height/2)&&
                readback->y_bytes>=readback->y_stride*v->height&&readback->uv_bytes>=readback->uv_stride*(v->height/2),
                "validation destination bounds mismatch");
        }
        __strong id<MTLBuffer> buffers[2]={nil,nil};
        const NSUInteger row=readback?((NSUInteger(v->width)+255)&~NSUInteger(255)):256;
        for(size_t plane=0;plane<2;++plane) {
            const NSUInteger h=readback?CVPixelBufferGetHeightOfPlane(owner->buffer,plane):1;
            buffers[plane]=readback?[c.device newBufferWithLength:row*h options:MTLResourceStorageModeShared]:c.samples[plane];
            require(buffers[plane]!=nil,"cannot allocate import probe readback buffer");
        }
        id<MTLCommandBuffer> command=[c.queue commandBuffer];require(command!=nil,"no Metal import command buffer");
        id<MTLBlitCommandEncoder> blit=[command blitCommandEncoder];require(blit!=nil,"no Metal import blit encoder");
        for(size_t plane=0;plane<2;++plane) {
            const NSUInteger w=readback?CVPixelBufferGetWidthOfPlane(owner->buffer,plane):1;
            const NSUInteger h=readback?CVPixelBufferGetHeightOfPlane(owner->buffer,plane):1;
            [blit copyFromTexture:owner->textures[plane] sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
                sourceSize:MTLSizeMake(w,h,1) toBuffer:buffers[plane] destinationOffset:0 destinationBytesPerRow:row destinationBytesPerImage:row*h];
        }
        [blit endEncoding];
        // Keep CVMetalTextureRef wrappers AND their CVPixelBuffer through GPU
        // completion, not just the raw MTLTexture. No callback captures Context.
        auto completion=std::make_shared<std::shared_ptr<Imported>>(owner);
        [command addCompletedHandler:^(id<MTLCommandBuffer> done){(void)done;completion->reset();}];
        [command commit];[command waitUntilCompleted];
        require(command.status==MTLCommandBufferStatusCompleted,"Metal import consumer failed; commands drained");
        if(readback)for(size_t plane=0;plane<2;++plane) {
            uint8_t *destination=plane?readback->uv:readback->y;
            const size_t stride=plane?readback->uv_stride:readback->y_stride;
            const size_t h=CVPixelBufferGetHeightOfPlane(owner->buffer,plane);
            const auto *source=static_cast<const uint8_t *>(buffers[plane].contents);
            for(size_t y=0;y<h;++y)std::memcpy(destination+y*stride,source+y*row,v->width);
        }
        ++c.counters->imports;
        if(readback)c.counters->validation+=(uint64_t)v->width*v->height*3/2;else c.counters->sampled+=3;
        message(error,capacity,"");return 0;
    }catch(const Unsupported &e){message(error,capacity,e.what());return 1;}
     catch(const std::exception &e){message(error,capacity,e.what());return -1;}} @catch(NSException *e){message(error,capacity,(e.reason?e.reason.UTF8String:"Metal import exception"));return -1;} }
}
void reset(void *handle){if(auto *c=static_cast<Context *>(handle)){CVMetalTextureCacheFlush(c->cache,0);++c->counters->resets;}}
int stats(void *handle,aji_apple_nv12_stats_v1 *out) {
    auto *c=static_cast<Context *>(handle);if(!c||!out||out->size<sizeof(*out))return -1;
    *out={sizeof(*out),1,c->device.registryID,c->counters->imports.load(),c->counters->live.load(),c->counters->peak.load(),
        c->counters->sampled.load(),c->counters->validation.load(),c->counters->resets.load()};return 0;
}
void destroy(void *handle){delete static_cast<Context *>(handle);}
const aji_apple_nv12_probe_api api={sizeof(api),1,create,query,consume,reset,stats,destroy};
}
extern "C" const aji_apple_nv12_probe_api *aji_apple_nv12_probe_api_v1(void){return &api;}
