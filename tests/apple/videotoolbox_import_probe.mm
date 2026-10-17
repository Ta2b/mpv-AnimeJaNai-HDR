#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <VideoToolbox/VideoToolbox.h>
#import <Metal/Metal.h>
#include "nv12_import_probe.h"
#include <cstdio>
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <vector>
namespace {
void check(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
struct Decoded {
    CVPixelBufferRef pixels=nullptr;OSStatus status=-1;CMTime pts=kCMTimeInvalid;
    void clear(){if(pixels)CVPixelBufferRelease(pixels);pixels=nullptr;status=-1;pts=kCMTimeInvalid;}
    ~Decoded(){clear();}
};
void decoded(void *opaque,void *,OSStatus status,VTDecodeInfoFlags,CVImageBufferRef image,CMTime pts,CMTime) {
    auto &r=*static_cast<Decoded *>(opaque);r.status=status;r.pts=pts;if(image)r.pixels=CVPixelBufferRetain(image);
}
struct Session {
    VTDecompressionSessionRef value=nullptr;
    ~Session(){if(value){VTDecompressionSessionWaitForAsynchronousFrames(value);VTDecompressionSessionInvalidate(value);CFRelease(value);}}
};
NSDictionary *metadata(CVPixelBufferRef p) {
    NSMutableDictionary *result=[NSMutableDictionary dictionary];
    for(NSString *key in @[(__bridge NSString *)kCVImageBufferColorPrimariesKey,(__bridge NSString *)kCVImageBufferTransferFunctionKey,
                           (__bridge NSString *)kCVImageBufferYCbCrMatrixKey,(__bridge NSString *)kCVImageBufferCleanApertureKey]) {
        CFTypeRef value=CVBufferGetAttachment(p,(__bridge CFStringRef)key,nullptr);
        result[key]=value?(__bridge id)value:[NSNull null];
    }
    return result;
}
}
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    @autoreleasepool {
        NSMutableDictionary *cases=[NSMutableDictionary dictionary];
        NSMutableDictionary *receipt=[@{@"passed":@NO,@"cases":cases,@"scope":@"Native VideoToolbox decoded NV12 -> Metal plane import only; no inference/renderer/FPS claim"}mutableCopy];
        auto save=[&]{NSData *json=[NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingPrettyPrinted error:nil];[json writeToFile:@(argv[2]) atomically:YES];};
        const aji_apple_nv12_probe_api *api=aji_apple_nv12_probe_api_v1();void *context=nullptr;
        try {
            receipt[@"os"]=[[NSProcessInfo processInfo]operatingSystemVersionString];
            id<MTLDevice> device=MTLCreateSystemDefaultDevice();receipt[@"metal_device"]=device.name?:@"unavailable";
            receipt[@"metal_registry_id"]=@(device.registryID);receipt[@"metal_unified"]=@(device.hasUnifiedMemory);
            receipt[@"hardware_hevc_advertised"]=@(VTIsHardwareDecodeSupported(kCMVideoCodecType_HEVC));
            receipt[@"hardware_h264_advertised"]=@(VTIsHardwareDecodeSupported(kCMVideoCodecType_H264));
            save();
            NSError *error=nil;AVURLAsset *asset=[AVURLAsset URLAssetWithURL:[NSURL fileURLWithPath:@(argv[1])] options:nil];
            AVAssetTrack *track=[[asset tracksWithMediaType:AVMediaTypeVideo] firstObject];check(track!=nil,"no compressed video track");
            AVAssetReader *reader=[[AVAssetReader alloc]initWithAsset:asset error:&error];check(reader!=nil,"cannot create compressed sample reader");
            AVAssetReaderTrackOutput *output=[[AVAssetReaderTrackOutput alloc]initWithTrack:track outputSettings:nil];output.alwaysCopiesSampleData=NO;
            [reader addOutput:output];check([reader startReading],"cannot read compressed samples");
            Decoded picture;Session session;
            auto nextSample=[&]() -> CMSampleBufferRef {
                for(int skipped=0;skipped<8;++skipped) {
                    CMSampleBufferRef value=[output copyNextSampleBuffer];
                    check(value!=nullptr,"missing compressed video sample");
                    CMFormatDescriptionRef format=CMSampleBufferGetFormatDescription(value);
                    receipt[@"sample_inspection"]=@{@"valid":@(CMSampleBufferIsValid(value)),@"ready":@(CMSampleBufferDataIsReady(value)),
                        @"samples":@(CMSampleBufferGetNumSamples(value)),@"bytes":@(CMSampleBufferGetTotalSampleSize(value)),
                        @"format_present":@(format!=nullptr),@"data_buffer_present":@(CMSampleBufferGetDataBuffer(value)!=nullptr),@"skipped":@(skipped)};
                    if(format){CFStringRef desc=CFCopyDescription(format);receipt[@"format_description"]=CFBridgingRelease(desc);}save();
                    if(format&&CMSampleBufferGetNumSamples(value)>0&&CMSampleBufferGetDataBuffer(value))return value;
                    // An empty edit/marker is not an encoded frame and cannot configure VT.
                    CFRelease(value);
                }
                throw std::runtime_error("No compressed frame after bounded marker scan");
            };
            CMSampleBufferRef sample=nextSample();
            VTDecompressionOutputCallbackRecord callback={decoded,&picture};
            NSDictionary *spec=@{(__bridge id)kVTVideoDecoderSpecification_EnableHardwareAcceleratedVideoDecoder:@YES};
            NSDictionary *attrs=@{(__bridge id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange),
                (__bridge id)kCVPixelBufferIOSurfacePropertiesKey:@{},(__bridge id)kCVPixelBufferMetalCompatibilityKey:@YES};
            OSStatus made=VTDecompressionSessionCreate(kCFAllocatorDefault,(CMVideoFormatDescriptionRef)CMSampleBufferGetFormatDescription(sample),
                (__bridge CFDictionaryRef)spec,(__bridge CFDictionaryRef)attrs,&callback,&session.value);
            NSMutableArray *attempts=[NSMutableArray arrayWithObject:@{@"requirements":@"NV12 IOSurface Metal-compatible; hardware optional",@"status":@(made)}];
            receipt[@"session_create_attempts"]=attempts;
            save();
            if(made!=noErr) {
                // Diagnose a rejected output constraint separately from codec availability.
                // Subsequent import checks still require the real decoded NV12 IOSurface.
                NSMutableDictionary *withoutMetal=[attrs mutableCopy];[withoutMetal removeObjectForKey:(__bridge id)kCVPixelBufferMetalCompatibilityKey];
                made=VTDecompressionSessionCreate(kCFAllocatorDefault,(CMVideoFormatDescriptionRef)CMSampleBufferGetFormatDescription(sample),
                    nullptr,(__bridge CFDictionaryRef)withoutMetal,&callback,&session.value);
                [attempts addObject:@{@"requirements":@"NV12 IOSurface; platform decoder",@"status":@(made)}];save();
            }
            if(made!=noErr) {
                made=VTDecompressionSessionCreate(kCFAllocatorDefault,(CMVideoFormatDescriptionRef)CMSampleBufferGetFormatDescription(sample),
                    nullptr,nullptr,&callback,&session.value);
                [attempts addObject:@{@"requirements":@"platform defaults; diagnosis only unless import contract holds",@"status":@(made)}];save();
            }
            if(made!=noErr){CFRelease(sample);throw std::runtime_error("VideoToolbox native decoder unavailable after minimal constraints: "+std::to_string(made));}
            CFTypeRef hardware=nullptr;
            OSStatus property=VTSessionCopyProperty(session.value,kVTDecompressionPropertyKey_UsingHardwareAcceleratedVideoDecoder,kCFAllocatorDefault,&hardware);
            receipt[@"hardware_decoder"]=property==noErr&&hardware?(__bridge id)hardware:[NSNull null];if(hardware)CFRelease(hardware);
            char why[256];context=api->create(why,sizeof why);check(context!=nullptr,why);
            VTDecodeInfoFlags flags=0;OSStatus status=VTDecompressionSessionDecodeFrame(session.value,sample,0,nullptr,&flags);
            VTDecompressionSessionWaitForAsynchronousFrames(session.value);
            CMTime source_pts=CMSampleBufferGetPresentationTimeStamp(sample);CFRelease(sample);
            check(status==noErr&&picture.status==noErr&&picture.pixels,"native VideoToolbox decode failed");
            check(CMTimeCompare(source_pts,picture.pts)==0,"VideoToolbox callback PTS mismatch");
            auto p=picture.pixels;const uint32_t w=(uint32_t)CVPixelBufferGetWidth(p),h=(uint32_t)CVPixelBufferGetHeight(p);size_t pitch=w+16;
            aji_apple_nv12_view_v1 view={sizeof(view),1,w,h,0,0,w,h,AJI_APPLE_NV12_SDR709,0,1,1,CMTimeGetSeconds(picture.pts)};
            check(api->query(context,p,&view,why,sizeof why)==0,why);
            NSDictionary *before=metadata(p);
            std::vector<uint8_t> reference_y(w*h),reference_uv(w*h/2),y(pitch*h,0xa5),uv(pitch*h/2,0xa5);
            check(CVPixelBufferLockBaseAddress(p,kCVPixelBufferLock_ReadOnly)==kCVReturnSuccess,"cannot read native reference planes");
            for(size_t plane=0;plane<2;++plane) {
                const auto *source=(const uint8_t *)CVPixelBufferGetBaseAddressOfPlane(p,plane);size_t stride=CVPixelBufferGetBytesPerRowOfPlane(p,plane),rows=plane?h/2:h;
                auto *destination=plane?reference_uv.data():reference_y.data();
                for(size_t row=0;row<rows;++row)std::memcpy(destination+row*w,source+row*stride,w);
            }
            CVPixelBufferUnlockBaseAddress(p,kCVPixelBufferLock_ReadOnly);
            aji_apple_nv12_readback_v1 readback={sizeof(readback),y.data(),uv.data(),pitch,pitch,y.size(),uv.size()};
            check(api->consume(context,p,&view,&readback,why,sizeof why)==0,why);
            for(size_t plane=0;plane<2;++plane) {
                const auto &actual=plane?uv:y;const auto &expected=plane?reference_uv:reference_y;size_t rows=plane?h/2:h;
                for(size_t row=0;row<rows;++row) {
                    check(!std::memcmp(actual.data()+row*pitch,expected.data()+row*w,w),"imported plane pixels differ");
                    for(size_t x=w;x<pitch;++x)check(actual[row*pitch+x]==0xa5,"plane readback wrote padding");
                }
            }
            check([before isEqualToDictionary:metadata(p)],"source color/crop attachments changed");
            aji_apple_nv12_stats_v1 stats={sizeof(stats)};check(api->stats(context,&stats)==0&&stats.live_images==0,"import owners still live after synchronous completion");
            cases[@"native_decoded_planes"]=@{@"exact":@YES,@"metadata_unchanged":@YES,@"pts_unchanged":@YES,@"width":@(w),@"height":@(h),@"live_images":@(stats.live_images),@"validation_bytes":@(stats.validation_bytes)};save();
            auto unsupported=view;unsupported.flags=0;
            std::fill(y.begin(),y.end(),0xa5);std::fill(uv.begin(),uv.end(),0xa5);
            check(api->consume(context,p,&unsupported,&readback,why,sizeof why)==1,"non-SDR709 did not request explicit fallback");
            CVPixelBufferRef ten=nullptr;
            NSMutableDictionary *tenattrs=[attrs mutableCopy];tenattrs[(__bridge id)kCVPixelBufferPixelFormatTypeKey]=@(kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange);
            check(CVPixelBufferCreate(kCFAllocatorDefault,w,h,kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange,(__bridge CFDictionaryRef)tenattrs,&ten)==kCVReturnSuccess,"cannot create P010 unsupported-format fixture");
            int refused=api->query(context,ten,&view,why,sizeof why);CVPixelBufferRelease(ten);check(refused==1,"P010 was not refused without truncation");
            auto invalid=readback;invalid.y_stride=w-1;
            check(api->consume(context,p,&view,&invalid,why,sizeof why)<0,"invalid destination bounds accepted");
            check(std::all_of(y.begin(),y.end(),[](uint8_t n){return n==0xa5;})&&std::all_of(uv.begin(),uv.end(),[](uint8_t n){return n==0xa5;}),"refused import wrote a partial result");
            api->stats(context,&stats);check(stats.live_images==0&&stats.imports==1,"refused imports leaked owners or counted success");
            cases[@"refusal_and_error"]=@{@"non_sdr709_fallback":@YES,@"p010_refused":@YES,@"invalid_bounds_refused":@YES,@"output_untouched":@YES,@"live_images":@(stats.live_images)};save();
            api->reset(context);picture.clear();sample=nextSample();
            status=VTDecompressionSessionDecodeFrame(session.value,sample,0,nullptr,&flags);VTDecompressionSessionWaitForAsynchronousFrames(session.value);source_pts=CMSampleBufferGetPresentationTimeStamp(sample);CFRelease(sample);
            check(status==noErr&&picture.status==noErr&&picture.pixels&&CMTimeCompare(source_pts,picture.pts)==0,"decoder/reset second-frame failure");
            view.generation=2;view.source=2;view.pts=CMTimeGetSeconds(picture.pts);
            check(api->consume(context,picture.pixels,&view,nullptr,why,sizeof why)==0,why);
            api->stats(context,&stats);check(stats.live_images==0&&stats.imports==2&&stats.resets==1&&stats.sampled_bytes==3,"reset or completion accounting mismatch");
            cases[@"reset_and_sample_consumer"]=@{@"imports":@(stats.imports),@"live_images":@(stats.live_images),@"peak_images":@(stats.peak_images),@"sampled_bytes":@(stats.sampled_bytes),@"resets":@(stats.resets)};
            receipt[@"passed"]=@YES;save();api->destroy(context);return 0;
        }catch(const std::exception &e){receipt[@"error"]=@(e.what());save();if(context)api->destroy(context);std::fprintf(stderr,"%s\n",e.what());return 1;}
    }
}
