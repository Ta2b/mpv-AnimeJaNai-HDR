// Executor: Core ML, without ONNX Runtime. The model is a Core ML ML Program whose input and
// output are 8-bit images; the package for the exact window size is made from the template of
// convert_models.py (mlpatch.h), compiled once and kept in the cache.
//
// The device is the caller's choice, exactly: ALL / AUTO (Core ML decides), GPU, ANE / NPU
// (Neural Engine) or CPU. Core ML always keeps the CPU as a fallback for an operation a
// processor cannot run; statistics report the preferred placement plan, not a per-frame device trace.
#import <Foundation/Foundation.h>
#import <Accelerate/Accelerate.h>
#import <CoreML/CoreML.h>
#import <CoreVideo/CoreVideo.h>
#include "engine.h"
#include "mlpatch.h"
#include "../common/placement_diagnostic.h"
#include "coreml_program_key.h"
#include "coreml_cache_transaction.h"
#include <cstdio>
#include <cstdlib>
#include <filesystem>

namespace aji {
namespace {

std::string text(NSError *error)
{
    return error ? std::string([[error localizedDescription] UTF8String]) : std::string("unknown error");
}

// The plan is a diagnostic of preferred placement, not a per-frame device trace.
// URL/configuration and state outlive the executor; callbacks never capture it.
struct PlanRequest {
    NSURL *__strong url=nil;
    MLModelConfiguration *__strong configuration=nil;
    std::shared_ptr<detail::PlacementState> state;
};
std::shared_ptr<detail::PlacementState> placement(NSURL *compiled,MLModelConfiguration *configuration,
    const detail::PlacementKey &key)
{
    using namespace detail;
    const char *disabled=std::getenv("AJI_COREML_NO_PLAN");
    if(disabled&&*disabled=='1')return std::make_shared<PlacementState>(PlacementStatus::Disabled,"disabled (AJI_COREML_NO_PLAN)");
    if (@available(macOS 14.4, *)) {
        static PlacementCache cache(16);
        auto entry=cache.get(key);if(!entry.start)return entry.state;
        auto request=std::make_shared<PlanRequest>();request->url=compiled;request->configuration=configuration;request->state=entry.state;
        // Even the API invocation runs outside configure. A cached or pending
        // identical request is shared; no per-executor thread and no join.
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0), ^{
          @autoreleasepool { @try {
            [MLComputePlan loadContentsOfURL:request->url configuration:request->configuration
                completionHandler:^(MLComputePlan *plan,NSError *error) {
              @autoreleasepool { @try {
                if(error||!plan) {
                    request->state->complete(PlacementStatus::Failed,"failed: "+text(error));return;
                }
                MLModelStructureProgramFunction *main=plan.modelStructure.program.functions[@"main"];
                if(!main){request->state->complete(PlacementStatus::Failed,"unavailable (no ML Program main in compute plan)");return;}
                NSUInteger gpu=0,neural=0,cpu=0,unknown=0;
                for(MLModelStructureProgramOperation *operation in main.block.operations) {
                    MLComputePlanDeviceUsage *usage=[plan computeDeviceUsageForMLProgramOperation:operation];
                    id<MLComputeDeviceProtocol> device=usage.preferredComputeDevice;
                    if(device==nil)continue; // constants
                    if([device isKindOfClass:[MLGPUComputeDevice class]])gpu++;
                    else if([device isKindOfClass:[MLNeuralEngineComputeDevice class]])neural++;
                    else if([device isKindOfClass:[MLCPUComputeDevice class]])cpu++;
                    else unknown++;
                }
                NSString *summary=[NSString stringWithFormat:@"plan: %lu GPU, %lu Neural Engine, %lu CPU preferred operations (%lu unclassified)",
                    (unsigned long)gpu,(unsigned long)neural,(unsigned long)cpu,(unsigned long)unknown];
                request->state->complete(PlacementStatus::Ready,std::string([summary UTF8String]));
              } @catch(NSException *exception) {
                request->state->complete(PlacementStatus::Failed,"failed: "+std::string([[exception reason] UTF8String]?:"Core ML diagnostic exception"));
              } }
            }];
          } @catch(NSException *exception) {
            request->state->complete(PlacementStatus::Failed,"failed: "+std::string([[exception reason] UTF8String]?:"Core ML diagnostic exception"));
          } }
        });
        return entry.state;
    }
    return std::make_shared<PlacementState>(PlacementStatus::Unavailable,"unavailable (requires macOS14.4)");
}

class CoreMLExecutor : public Executor {
public:
    explicit CoreMLExecutor(const ExecutorRequest &r) : w_(r.width), h_(r.height)
    {
        @autoreleasepool {
            namespace fs = std::filesystem;
            const std::string device = lower(r.device);
            MLComputeUnits units = MLComputeUnitsAll;
            label = "Core ML/AUTO";
            if (device == "gpu") { units = MLComputeUnitsCPUAndGPU; label = "Core ML/GPU"; }
            else if (device == "ane" || device == "npu") { units = MLComputeUnitsCPUAndNeuralEngine; label = "Core ML/NPU"; }
            else if (device == "cpu") { units = MLComputeUnitsCPUOnly; label = "Core ML/CPU"; }

            // One compiled model per model, size and template: the compute units are chosen when
            // it is loaded, not when it is compiled.
            require(!r.cache_dir.empty(), "Core ML: no cache folder for compiled models");
            const std::string content = coreml_template_tag(r.models_dir, r.model);
            NSString *build = [[NSProcessInfo processInfo] operatingSystemVersionString];
            NSString *framework = [[[NSBundle bundleForClass:[MLModel class]] objectForInfoDictionaryKey:@"CFBundleVersion"] description];
            coreml::CompileEnvironment environment;
            environment.os_build=std::string([build UTF8String]);
            // A framework without its own version is still identified by the
            // observed system build; never substitute a floating SDK label.
            environment.framework_version=framework.length?std::string([framework UTF8String]):"system-build/"+environment.os_build;
#if defined(__arm64__) || defined(__aarch64__)
            environment.host_architecture="arm64";
#elif defined(__x86_64__)
            environment.host_architecture="x86_64";
#else
#error Unsupported Core ML host compiler architecture
#endif
            const std::string program=coreml::program_key(content,w_,h_,environment);
            std::fprintf(stderr,"[aji] Core ML cache identity: p3-%s template %s compiler %s runtime %s host %s\n",
                program.c_str(),content.c_str(),environment.framework_version.c_str(),environment.os_build.c_str(),environment.host_architecture.c_str());
            coreml::cache::Store store(r.cache_dir,program);
            const auto entry=store.acquire([&](const fs::path &stage) {
                std::fprintf(stderr,"[aji] Core ML compiled cache miss: %s content %s; rebuilding\n",r.model.c_str(),content.c_str());
                // Freeze the exact source whose identity we are about to use.
                // The neutral outer name is not part of template identity.
                const auto snapshot=stage/"source";
                fs::create_directory(snapshot);
                const auto source=fs::path(r.models_dir);
                fs::copy(source/(r.model+".mlpackage"),snapshot/"template.mlpackage",fs::copy_options::recursive);
                fs::copy_file(source/(r.model+".mlpatch"),snapshot/"template.mlpatch");
                require(coreml_template_tag(snapshot.string(),"template")==content,
                    "Core ML template changed during snapshot; reopen the video to retry");
                const auto package=stage/"model.mlpackage";
                write_coreml_package(snapshot.string(),"template",w_,h_,package.string());
                @autoreleasepool {
                    NSError *error=nil;
                    NSURL *made=[MLModel compileModelAtURL:[NSURL fileURLWithPath:@(package.string().c_str())] error:&error];
                    require(made!=nil,"Core ML could not compile the model: "+text(error));
                    NSURL *kept=[NSURL fileURLWithPath:@((stage/"model.mlmodelc").string().c_str())];
                    require([[NSFileManager defaultManager] moveItemAtURL:made toURL:kept error:&error],
                        "Core ML: could not stage the compiled model: "+text(error));
                    MLModelConfiguration *validation=[[MLModelConfiguration alloc] init];
                    validation.computeUnits=MLComputeUnitsCPUOnly;
                    MLModel *validated=[MLModel modelWithContentsOfURL:kept configuration:validation error:&error];
                    require(validated!=nil,"Core ML compiled artifact failed native validation: "+text(error));
                }
                fs::remove_all(snapshot);
                fs::remove_all(package);
            });
            std::fprintf(stderr,"[aji] Core ML committed cache: %s generation %s\n",program.c_str(),entry.generation.c_str());
            NSURL *url=[NSURL fileURLWithPath:@(entry.compiled().string().c_str())];
            NSError *error=nil;
            MLModelConfiguration *configuration = [[MLModelConfiguration alloc] init];
            configuration.computeUnits = units;
            // Permit lower-precision GPU accumulation by default; FP16 weights
            // do not establish the accumulator type or numerical equivalence.
            // AJI_COREML_PRECISE=1 disables that permission for comparison. The
            // actual kernel precision still needs native qualification.
            const char *precise = std::getenv("AJI_COREML_PRECISE");
            configuration.allowLowPrecisionAccumulationOnGPU = !(precise && *precise == '1');
            if (@available(macOS 14.4, *)) {
                // The size never changes after loading, and time spent preparing the model is
                // well spent: it is loaded once per video.
                MLOptimizationHints *hints = [[MLOptimizationHints alloc] init];
                hints.reshapeFrequency = MLReshapeFrequencyHintInfrequent;
                if (@available(macOS 15.0, *)) {
                    const char *plain = std::getenv("AJI_COREML_DEFAULT_STRATEGY");
                    if (!(plain && *plain == '1')) hints.specializationStrategy = MLSpecializationStrategyFastPrediction;
                }
                configuration.optimizationHints = hints;
            }
            model_ = [MLModel modelWithContentsOfURL:url configuration:configuration error:&error];
            if (model_ == nil) {
                const auto failure=text(error);
                // Device/hint failures do not prove artifact corruption. Only
                // retire the commit if independent CPU loading fails too.
                MLModelConfiguration *validation=[[MLModelConfiguration alloc] init];
                validation.computeUnits=MLComputeUnitsCPUOnly;
                NSError *validation_error=nil;
                MLModel *validated=[MLModel modelWithContentsOfURL:url configuration:validation error:&validation_error];
                if(validated==nil) {
                    store.retire(entry);
                    throw std::runtime_error("Core ML could not load the model (invalid commit retired, data preserved; reopen to rebuild): "+failure);
                }
                throw std::runtime_error("Core ML could not load the requested configuration (CPU artifact valid, cache preserved): "+failure);
            }
            NSDictionary *attributes = @{(id)kCVPixelBufferIOSurfacePropertiesKey: @{}, (id)kCVPixelBufferMetalCompatibilityKey: @YES};
            require(CVPixelBufferCreate(kCFAllocatorDefault, (size_t)w_, (size_t)h_, kCVPixelFormatType_32BGRA,
                                        (__bridge CFDictionaryRef)attributes, &in_) == kCVReturnSuccess
                    && CVPixelBufferCreate(kCFAllocatorDefault, (size_t)(2 * w_), (size_t)(2 * h_), kCVPixelFormatType_32BGRA,
                                           (__bridge CFDictionaryRef)attributes, &out_) == kCVReturnSuccess,
                    "Core ML: could not allocate the picture buffers");
            options_ = [[MLPredictionOptions alloc] init];
            // Core ML writes the result into this buffer instead of allocating one per picture.
            options_.outputBackings = @{@"output": (__bridge id)out_};
            detail::PlacementKey key;
            key.template_content="p3-"+program;key.model=r.model;key.width=w_;key.height=h_;
            key.units=(int)configuration.computeUnits;key.low_precision=configuration.allowLowPrecisionAccumulationOnGPU?1:0;
            key.os_build=std::string([[[NSProcessInfo processInfo] operatingSystemVersionString] UTF8String]);
            if (@available(macOS 14.4, *))key.reshape=(int)configuration.optimizationHints.reshapeFrequency;
            if (@available(macOS 15.0, *))key.specialization=(int)configuration.optimizationHints.specializationStrategy;
            note="unavailable (diagnostic initialization failed)"; // immutable fallback
            try { placement_=placement(url,configuration,key); }
            catch(const std::exception &error) {std::fprintf(stderr,"[aji] Core ML placement diagnostic unavailable: %s\n",error.what());}
        }
    }

    ~CoreMLExecutor() override
    {
        if (in_) CVPixelBufferRelease(in_);
        if (out_) CVPixelBufferRelease(out_);
    }

    std::string placement_note() const override {return placement_?placement_->snapshot().message:note;}

    void run(const Job &job) override
    {
        @autoreleasepool {
            // Accelerate converts on several cores unless told not to: only when this executor
            // is the one working.
            const vImage_Flags flags = job.spread ? kvImageNoFlags : kvImageDoNotTile;
            require(CVPixelBufferLockBaseAddress(in_, 0) == kCVReturnSuccess, "Core ML: input buffer not accessible");
            vImage_Buffer rgb = {(void *)job.in, (vImagePixelCount)h_, (vImagePixelCount)w_, (size_t)job.in_stride};
            vImage_Buffer bgra = {CVPixelBufferGetBaseAddress(in_), (vImagePixelCount)h_, (vImagePixelCount)w_, CVPixelBufferGetBytesPerRow(in_)};
            const vImage_Error packed = vImageConvert_RGB888toBGRA8888(&rgb, NULL, 255, &bgra, false, flags);
            CVPixelBufferUnlockBaseAddress(in_, 0);
            require(packed == kvImageNoError, "Core ML: could not convert the input picture");

            NSError *error = nil;
            MLDictionaryFeatureProvider *features =
                [[MLDictionaryFeatureProvider alloc] initWithDictionary:@{@"input": [MLFeatureValue featureValueWithPixelBuffer:in_]}
                                                                  error:&error];
            require(features != nil, "Core ML: " + text(error));
            id<MLFeatureProvider> result = [model_ predictionFromFeatures:features options:options_ error:&error];
            require(result != nil, "Core ML prediction failed: " + text(error));
            CVPixelBufferRef picture = [[result featureValueForName:@"output"] imageBufferValue];
            require(picture != NULL, "Core ML returned no picture");
            require(CVPixelBufferGetPixelFormatType(picture) == kCVPixelFormatType_32BGRA
                    && CVPixelBufferGetWidth(picture) == (size_t)(2 * w_) && CVPixelBufferGetHeight(picture) == (size_t)(2 * h_),
                    "Core ML returned a picture of an unexpected format or size");
            require(CVPixelBufferLockBaseAddress(picture, kCVPixelBufferLock_ReadOnly) == kCVReturnSuccess,
                    "Core ML: output buffer not accessible");
            const size_t row = CVPixelBufferGetBytesPerRow(picture);
            uint8_t *base = (uint8_t *)CVPixelBufferGetBaseAddress(picture);
            vImage_Buffer from = {base + (size_t)job.crop_y * row + (size_t)job.crop_x * 4,
                                  (vImagePixelCount)job.crop_h, (vImagePixelCount)job.crop_w, row};
            vImage_Buffer to = {job.out, (vImagePixelCount)job.crop_h, (vImagePixelCount)job.crop_w, (size_t)job.out_stride};
            const vImage_Error unpacked = vImageConvert_BGRA8888toRGB888(&from, &to, flags);
            CVPixelBufferUnlockBaseAddress(picture, kCVPixelBufferLock_ReadOnly);
            require(unpacked == kvImageNoError, "Core ML: could not convert the output picture");
        }
    }

private:
    std::shared_ptr<detail::PlacementState> placement_;
    int w_, h_;
    MLModel *model_ = nil;
    MLPredictionOptions *options_ = nil;
    CVPixelBufferRef in_ = NULL, out_ = NULL;
};

} // namespace

std::unique_ptr<Executor> make_coreml_executor(const ExecutorRequest &request)
{
    return std::make_unique<CoreMLExecutor>(request);
}

} // namespace aji
