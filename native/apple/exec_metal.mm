// Executor: Metal, through Metal Performance Shaders Graph. The network of NAME.ajm is built as
// a graph for the exact window size and runs on the GPU in half floats.
//
// The bytes go to the GPU and come back as bytes: the conversion from 8-bit RGB to half floats,
// the layout change and the way back (clamp, x255, round, 8-bit) are part of the graph, so the
// processor only copies rows.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalPerformanceShaders/MetalPerformanceShaders.h>
#import <MetalPerformanceShadersGraph/MetalPerformanceShadersGraph.h>
#include "ajm.h"
#include "engine.h"
#include <cstdlib>
#include <atomic>
#include <cstring>
#include <string>

namespace aji {
namespace {

const uint16_t kHalfOne = 0x3C00;   // 1.0 as a half float

struct MetalImage final : ResidentImage {
    __strong MPSGraphTensorData *tensor=nil;
    MetalImage(MPSGraphTensorData *value,int w,int h,uint64_t id) : tensor(value) {
        width=w;height=h;device=id;
    }
};

class MetalExecutor : public Executor {
public:
    explicit MetalExecutor(const ExecutorRequest &r) : w_(r.width), h_(r.height)
    {
        @autoreleasepool {
            // Rows of pixels (NHWC) are what the pictures already are and what Metal's kernels
            // work on: the graph then needs no layout change. AJI_METAL_LAYOUT=nchw keeps the
            // layout of the model file, with a change of layout at each end (for a comparison).
            const char *layout = std::getenv("AJI_METAL_LAYOUT");
            nhwc_ = !(layout && std::string(layout) == "nchw");
            model_ = load_ajm(r.models_dir + "/" + r.model + ".ajm");
            device_ = MTLCreateSystemDefaultDevice();
            require(device_ != nil, "Metal: no GPU available");
            queue_ = [device_ newCommandQueue];
            require(queue_ != nil, "Metal: could not create a command queue");
            graph_device_ = [MPSGraphDevice deviceWithMTLDevice:device_];
            build();
            in_.resize((size_t)w_ * h_ * 3);
            out_.resize((size_t)4 * w_ * h_ * 3);
            label = "Metal/GPU";
            note = std::string("whole network on ") + [[device_ name] UTF8String] + ", half floats, "
                + (nhwc_ ? "rows of pixels (NHWC)" : "planes (NCHW)");
        }
    }

    void run(const Job &job) override
    {
        auto result=run_resident(job);
        read_resident(*result,job);
    }

    bool can_take_resident(const Executor &source) const override
    {
        const auto *other=dynamic_cast<const MetalExecutor *>(&source);
        return other && device_.registryID==other->device_.registryID &&
            w_==2*other->w_ && h_==2*other->h_;
    }

    std::unique_ptr<ResidentImage> run_resident(const Job &job,const ResidentImage *source=nullptr) override
    {
        @autoreleasepool {
            MPSGraphTensorData *feed=nil;
            if(source) {
                const auto *image=dynamic_cast<const MetalImage *>(source);
                require(image && image->device==device_.registryID && image->width==w_ && image->height==h_ &&
                    image->format==ResidentImage::Format::RGB8NHWC && image->memory==ResidentImage::Memory::MetalGraph,
                    "Metal: incompatible resident image");
                feed=image->tensor;
                require(feed.dataType==MPSDataTypeUInt8 && [feed.shape isEqualToArray:in_shape_],
                    "Metal: resident tensor type or shape mismatch");
            } else {
                require(job.in && (job.in_stride>=(ptrdiff_t)w_*3 || job.in_stride<=-(ptrdiff_t)w_*3),"Metal: invalid host input");
                const size_t row=(size_t)w_*3;
                for(int y=0;y<h_;++y)std::memcpy(in_.data()+(size_t)y*row,job.in+(ptrdiff_t)y*job.in_stride,row);
                staging_bytes_.fetch_add(in_.size(),std::memory_order_relaxed);
                NSData *bytes=[NSData dataWithBytesNoCopy:in_.data() length:in_.size() freeWhenDone:NO];
                feed=[[MPSGraphTensorData alloc] initWithDevice:graph_device_ data:bytes shape:in_shape_ dataType:MPSDataTypeUInt8];
            }
            MPSGraphTensorData *result=nil;
            // Both APIs are synchronous: the owner remains alive through the
            // next graph's call, without another queue/fence/worker protocol.
            if(executable_!=nil) {
                NSArray<MPSGraphTensorData *> *results=[executable_ runWithMTLCommandQueue:queue_ inputsArray:@[feed]
                    resultsArray:nil executionDescriptor:nil];
                require(results.count==1,"Metal: the graph returned no result");result=results[0];
            } else {
                NSDictionary<MPSGraphTensor *,MPSGraphTensorData *> *results=
                    [graph_ runWithMTLCommandQueue:queue_ feeds:@{input_:feed} targetTensors:@[output_] targetOperations:nil];
                result=results[output_];
            }
            require(result && result.dataType==MPSDataTypeUInt8 &&
                [result.shape isEqualToArray:@[@1,@(2*h_),@(2*w_),@3]],"Metal: invalid graph output");
            return std::make_unique<MetalImage>(result,2*w_,2*h_,device_.registryID);
        }
    }

    void read_resident(const ResidentImage &source,const Job &job) override
    {
        @autoreleasepool {
            const auto *image=dynamic_cast<const MetalImage *>(&source);
            require(image && image->device==device_.registryID && image->width==2*w_ && image->height==2*h_,
                "Metal: incompatible readback image");
            require(job.out && job.crop_x>=0 && job.crop_y>=0 && job.crop_w>=0 && job.crop_h>=0 &&
                job.crop_x+job.crop_w<=2*w_ && job.crop_y+job.crop_h<=2*h_ &&
                (job.out_stride>=(ptrdiff_t)job.crop_w*3 || job.out_stride<=-(ptrdiff_t)job.crop_w*3),"Metal: invalid output crop");
            MPSNDArray *array=[image->tensor mpsndarray];require(array!=nil,"Metal: the result is not readable");
            [array readBytes:out_.data() strideBytes:nil];
            readback_bytes_.fetch_add(out_.size(),std::memory_order_relaxed);
            const size_t row=(size_t)2*w_*3;
            for(int y=0;y<job.crop_h;++y)
                std::memcpy(job.out+(ptrdiff_t)y*job.out_stride,
                    out_.data()+(size_t)(y+job.crop_y)*row+(size_t)job.crop_x*3,(size_t)job.crop_w*3);
        }
    }
    ExecutorTransfers transfers() const override {
        return {staging_bytes_.load(std::memory_order_relaxed),readback_bytes_.load(std::memory_order_relaxed)};
    }

private:
    MPSGraphTensor *constant(const uint16_t *values, NSArray<NSNumber *> *shape, size_t count)
    {
        NSData *data = [NSData dataWithBytes:values length:count * sizeof(uint16_t)];
        return [graph_ constantWithData:data shape:shape dataType:MPSDataTypeFloat16];
    }

    // Convolution weights of the model file (out, in, rows, columns) in the graph's layout.
    MPSGraphTensor *kernel(const uint16_t *oihw, int o, int i, int k)
    {
        const size_t count = (size_t)o * i * k * k;
        if (!nhwc_) return constant(oihw, @[@(o), @(i), @(k), @(k)], count);
        std::vector<uint16_t> hwio(count);
        for (int a = 0; a < o; a++)
            for (int b = 0; b < i; b++)
                for (int y = 0; y < k; y++)
                    for (int x = 0; x < k; x++)
                        hwio[(((size_t)y * k + x) * i + b) * o + a] = oihw[(((size_t)a * i + b) * k + y) * k + x];
        return constant(hwio.data(), @[@(k), @(k), @(i), @(o)], count);
    }

    MPSGraphTensor *convolution(MPSGraphTensor *x, MPSGraphTensor *weights, int stride, int pad)
    {
        MPSGraphConvolution2DOpDescriptor *d = [MPSGraphConvolution2DOpDescriptor
            descriptorWithStrideInX:(NSUInteger)stride strideInY:(NSUInteger)stride dilationRateInX:1 dilationRateInY:1 groups:1
                        paddingLeft:(NSUInteger)pad paddingRight:(NSUInteger)pad paddingTop:(NSUInteger)pad paddingBottom:(NSUInteger)pad
                       paddingStyle:MPSGraphPaddingStyleExplicit
                         dataLayout:nhwc_ ? MPSGraphTensorNamedDataLayoutNHWC : MPSGraphTensorNamedDataLayoutNCHW
                      weightsLayout:nhwc_ ? MPSGraphTensorNamedDataLayoutHWIO : MPSGraphTensorNamedDataLayoutOIHW];
        require(d != nil, "Metal: could not describe a convolution");
        return [graph_ convolution2DWithSourceTensor:x weightsTensor:weights descriptor:d name:nil];
    }

    void build()
    {
        graph_ = [[MPSGraph alloc] init];
        in_shape_ = @[@1, @(h_), @(w_), @3];
        input_ = [graph_ placeholderWithShape:in_shape_ dataType:MPSDataTypeUInt8 name:@"input"];
        // Bytes, rows of RGB pixels -> half floats 0..1, one plane per colour.
        MPSGraphTensor *x = [graph_ castTensor:input_ toType:MPSDataTypeFloat16 name:nil];
        x = [graph_ multiplicationWithPrimaryTensor:x
                                    secondaryTensor:[graph_ constantWithScalar:1.0 / 255.0 dataType:MPSDataTypeFloat16] name:nil];
        if (!nhwc_) {
            x = [graph_ transposeTensor:x dimension:1 withDimension:3 name:nil];   // N C W H
            x = [graph_ transposeTensor:x dimension:2 withDimension:3 name:nil];   // N C H W
        }
        const NSUInteger channels = nhwc_ ? 3 : 1, rows = nhwc_ ? 1 : 2, columns = nhwc_ ? 2 : 3;

        std::vector<MPSGraphTensor *> t((size_t)model_.tensors, nil);
        t[0] = x;
        for (const auto &op : model_.ops) {
            MPSGraphTensor *a = t[(size_t)op.in[0]];
            MPSGraphTensor *result = nil;
            switch (op.kind) {
            case AjmOp::Unshuffle: {
                // out[c*4 + dy*2 + dx, y, x] = in[c, 2y + dy, 2x + dx], as a 2x2 convolution of
                // stride 2 whose weights are ones and zeros.
                std::vector<uint16_t> k((size_t)12 * 3 * 2 * 2, 0);
                for (int c = 0; c < 3; c++)
                    for (int dy = 0; dy < 2; dy++)
                        for (int dx = 0; dx < 2; dx++)
                            k[(size_t)(((c * 4 + dy * 2 + dx) * 3 + c) * 2 + dy) * 2 + dx] = kHalfOne;
                result = convolution(a, kernel(k.data(), 12, 3, 2), 2, 0);
                break;
            }
            case AjmOp::Conv: {
                MPSGraphTensor *weights = kernel(model_.weights.data() + op.weight, op.o, op.i, op.k);
                MPSGraphTensor *bias = constant(model_.weights.data() + op.bias,
                                                nhwc_ ? @[@1, @1, @1, @(op.o)] : @[@1, @(op.o), @1, @1], (size_t)op.o);
                result = [graph_ additionWithPrimaryTensor:convolution(a, weights, op.stride, op.pad) secondaryTensor:bias name:nil];
                break;
            }
            case AjmOp::Relu: result = [graph_ reLUWithTensor:a name:nil]; break;
            case AjmOp::Tanh: result = [graph_ tanhWithTensor:a name:nil]; break;
            case AjmOp::Sigmoid: result = [graph_ sigmoidWithTensor:a name:nil]; break;
            case AjmOp::Add: result = [graph_ additionWithPrimaryTensor:a secondaryTensor:t[(size_t)op.in[1]] name:nil]; break;
            case AjmOp::Mul: result = [graph_ multiplicationWithPrimaryTensor:a secondaryTensor:t[(size_t)op.in[1]] name:nil]; break;
            case AjmOp::Concat: {
                NSMutableArray<MPSGraphTensor *> *parts = [NSMutableArray array];
                for (int s : op.in) [parts addObject:t[(size_t)s]];
                result = [graph_ concatTensors:parts dimension:(NSInteger)channels name:nil];
                break;
            }
            case AjmOp::Shuffle:
                // out[c, y*r + dy, x*r + dx] = in[c*r*r + dy*r + dx, y, x]: the pixel-shuffle order.
                result = [graph_ depthToSpace2DTensor:a widthAxis:columns heightAxis:rows depthAxis:channels blockSize:(NSUInteger)op.factor
                                 usePixelShuffleOrder:YES name:nil];
                break;
            }
            require(result != nil, "Metal: an operation of the model could not be built");
            t[(size_t)op.out] = result;
        }
        // Back to bytes: 0..1 -> 0..255 rounded, rows of RGB pixels.
        MPSGraphTensor *y = t[(size_t)model_.output];
        y = [graph_ clampWithTensor:y minValueTensor:[graph_ constantWithScalar:0.0 dataType:MPSDataTypeFloat16]
                     maxValueTensor:[graph_ constantWithScalar:1.0 dataType:MPSDataTypeFloat16] name:nil];
        y = [graph_ multiplicationWithPrimaryTensor:y
                                    secondaryTensor:[graph_ constantWithScalar:255.0 dataType:MPSDataTypeFloat16] name:nil];
        y = [graph_ roundWithTensor:y name:nil];
        if (!nhwc_) {
            y = [graph_ transposeTensor:y dimension:1 withDimension:2 name:nil];   // N H C W
            y = [graph_ transposeTensor:y dimension:2 withDimension:3 name:nil];   // N H W C
        }
        output_ = [graph_ castTensor:y toType:MPSDataTypeUInt8 name:@"output"];

        // Compiled once for this size. Level 0 keeps every operation on the GPU; AJI_METAL_OPT=1
        // lets the graph also place operations on the other processors (for trials).
        const char *level = std::getenv("AJI_METAL_OPT");
        MPSGraphCompilationDescriptor *compilation = [[MPSGraphCompilationDescriptor alloc] init];
        compilation.optimizationLevel = level && *level == '1' ? MPSGraphOptimizationLevel1 : MPSGraphOptimizationLevel0;
        MPSGraphShapedType *type = [[MPSGraphShapedType alloc] initWithShape:in_shape_ dataType:MPSDataTypeUInt8];
        executable_ = [graph_ compileWithDevice:graph_device_ feeds:@{input_: type} targetTensors:@[output_]
                               targetOperations:nil compilationDescriptor:compilation];
    }

    int w_, h_;
    bool nhwc_ = true;
    AjmModel model_;
    id<MTLDevice> device_ = nil;
    id<MTLCommandQueue> queue_ = nil;
    MPSGraphDevice *graph_device_ = nil;
    MPSGraph *graph_ = nil;
    MPSGraphTensor *input_ = nil, *output_ = nil;
    MPSGraphExecutable *executable_ = nil;
    NSArray<NSNumber *> *in_shape_ = nil;
    std::vector<uint8_t> in_, out_;
    std::atomic<uint64_t> staging_bytes_{0},readback_bytes_{0};
};

} // namespace

std::unique_ptr<Executor> make_metal_executor(const ExecutorRequest &request)
{
    return std::make_unique<MetalExecutor>(request);
}

} // namespace aji
