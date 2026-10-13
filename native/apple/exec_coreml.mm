// Executor: Core ML, without ONNX Runtime. The model is a Core ML ML Program whose input and
// output are 8-bit images; the package for the exact window size is made from the template of
// convert_models.py (mlpatch.h), compiled once and kept in the cache.
//
// The device is the caller's choice, exactly: ALL / AUTO (Core ML decides), GPU, ANE / NPU
// (Neural Engine) or CPU. Core ML always keeps the CPU as a fallback for an operation a
// processor cannot run; where the model really runs is reported in the statistics (Placement).
#import <Foundation/Foundation.h>
#import <Accelerate/Accelerate.h>
#import <CoreML/CoreML.h>
#import <CoreVideo/CoreVideo.h>
#include "engine.h"
#include "mlpatch.h"
#include <cstdlib>
#include <filesystem>

namespace aji {
namespace {

std::string text(NSError *error)
{
    return error ? std::string([[error localizedDescription] UTF8String]) : std::string("unknown error");
}

// How many operations Core ML plans to run on each processor (macOS 14.4 and later).
std::string placement(NSURL *compiled, MLModelConfiguration *configuration)
{
    if (@available(macOS 14.4, *)) {
        __block NSString *summary = nil;
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        [MLComputePlan loadContentsOfURL:compiled configuration:configuration
                       completionHandler:^(MLComputePlan *plan, NSError *error) {
            (void)error;
            MLModelStructureProgramFunction *main = plan.modelStructure.program.functions[@"main"];
            if (main != nil) {
                NSUInteger gpu = 0, neural = 0, cpu = 0;
                for (MLModelStructureProgramOperation *operation in main.block.operations) {
                    MLComputePlanDeviceUsage *usage = [plan computeDeviceUsageForMLProgramOperation:operation];
                    id<MLComputeDeviceProtocol> device = usage.preferredComputeDevice;
                    if (device == nil) continue;   // constants
                    if ([device isKindOfClass:[MLGPUComputeDevice class]]) gpu++;
                    else if ([device isKindOfClass:[MLNeuralEngineComputeDevice class]]) neural++;
                    else cpu++;
                }
                summary = [NSString stringWithFormat:@"%lu operations on the GPU, %lu on the Neural Engine, %lu on the CPU",
                                                     (unsigned long)gpu, (unsigned long)neural, (unsigned long)cpu];
            }
            dispatch_semaphore_signal(done);
        }];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(20 * NSEC_PER_SEC))) == 0 && summary != nil)
            return std::string([summary UTF8String]);
    }
    return "";
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
            const fs::path folder = fs::path(r.cache_dir) / "native"
                / (r.model + "-" + std::to_string(w_) + "x" + std::to_string(h_) + "-" + coreml_template_tag(r.models_dir, r.model));
            const fs::path compiled = folder / "model.mlmodelc";
            NSError *error = nil;
            NSFileManager *files = [NSFileManager defaultManager];
            if (!fs::is_directory(compiled)) {
                const fs::path package = folder / "model.mlpackage";
                write_coreml_package(r.models_dir, r.model, w_, h_, package.string());
                NSURL *made = [MLModel compileModelAtURL:[NSURL fileURLWithPath:@(package.string().c_str())] error:&error];
                require(made != nil, "Core ML could not compile the model: " + text(error));
                // Core ML compiles into a temporary folder: kept under the cache instead.
                NSURL *kept = [NSURL fileURLWithPath:@(compiled.string().c_str())];
                [files removeItemAtURL:kept error:nil];
                require([files moveItemAtURL:made toURL:kept error:&error], "Core ML: could not keep the compiled model: " + text(error));
                std::error_code ignored;
                fs::remove_all(package, ignored);
            }
            NSURL *url = [NSURL fileURLWithPath:@(compiled.string().c_str())];
            MLModelConfiguration *configuration = [[MLModelConfiguration alloc] init];
            configuration.computeUnits = units;
            // Half-float sums in the GPU convolutions: the precision the model already uses.
            // AJI_COREML_PRECISE=1 keeps single-float sums (for a comparison).
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
                // A compiled model left by an interrupted run: once more from the template.
                std::error_code ignored;
                fs::remove_all(folder, ignored);
                throw std::runtime_error("Core ML could not load the model (cache cleared, try again): " + text(error));
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
            const char *no_plan = std::getenv("AJI_COREML_NO_PLAN");
            if (!(no_plan && *no_plan == '1')) note = placement(url, configuration);
        }
    }

    ~CoreMLExecutor() override
    {
        if (in_) CVPixelBufferRelease(in_);
        if (out_) CVPixelBufferRelease(out_);
    }

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
