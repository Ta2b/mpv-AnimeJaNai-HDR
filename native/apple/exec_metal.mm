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
#include <cstring>

namespace aji {
namespace {

const uint16_t kHalfOne = 0x3C00;   // 1.0 as a half float

class MetalExecutor : public Executor {
public:
    explicit MetalExecutor(const ExecutorRequest &r) : w_(r.width), h_(r.height)
    {
        @autoreleasepool {
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
            note = std::string("whole network on ") + [[device_ name] UTF8String] + ", half floats";
        }
    }

    void run(const Job &job) override
    {
        @autoreleasepool {
            const size_t row = (size_t)w_ * 3;
            for (int y = 0; y < h_; y++) std::memcpy(in_.data() + (size_t)y * row, job.in + (ptrdiff_t)y * job.in_stride, row);
            NSData *bytes = [NSData dataWithBytesNoCopy:in_.data() length:in_.size() freeWhenDone:NO];
            MPSGraphTensorData *feed = [[MPSGraphTensorData alloc] initWithDevice:graph_device_ data:bytes
                                                                            shape:in_shape_ dataType:MPSDataTypeUInt8];
            MPSGraphTensorData *result = nil;
            if (executable_ != nil) {
                NSArray<MPSGraphTensorData *> *results = [executable_ runWithMTLCommandQueue:queue_ inputsArray:@[feed]
                                                                                  resultsArray:nil executionDescriptor:nil];
                require(results.count == 1, "Metal: the graph returned no result");
                result = results[0];
            } else {
                NSDictionary<MPSGraphTensor *, MPSGraphTensorData *> *results =
                    [graph_ runWithMTLCommandQueue:queue_ feeds:@{input_: feed} targetTensors:@[output_] targetOperations:nil];
                result = results[output_];
            }
            require(result != nil, "Metal: the graph returned no result");
            MPSNDArray *array = [result mpsndarray];
            require(array != nil, "Metal: the result is not readable");
            [array readBytes:out_.data() strideBytes:nil];
            const size_t out_row = (size_t)2 * w_ * 3;
            for (int y = 0; y < job.crop_h; y++)
                std::memcpy(job.out + (ptrdiff_t)y * job.out_stride,
                            out_.data() + (size_t)(y + job.crop_y) * out_row + (size_t)job.crop_x * 3, (size_t)job.crop_w * 3);
        }
    }

private:
    MPSGraphTensor *constant(const uint16_t *values, NSArray<NSNumber *> *shape, size_t count)
    {
        NSData *data = [NSData dataWithBytes:values length:count * sizeof(uint16_t)];
        return [graph_ constantWithData:data shape:shape dataType:MPSDataTypeFloat16];
    }

    MPSGraphTensor *convolution(MPSGraphTensor *x, MPSGraphTensor *weights, int stride, int pad)
    {
        MPSGraphConvolution2DOpDescriptor *d = [MPSGraphConvolution2DOpDescriptor
            descriptorWithStrideInX:(NSUInteger)stride strideInY:(NSUInteger)stride dilationRateInX:1 dilationRateInY:1 groups:1
                        paddingLeft:(NSUInteger)pad paddingRight:(NSUInteger)pad paddingTop:(NSUInteger)pad paddingBottom:(NSUInteger)pad
                       paddingStyle:MPSGraphPaddingStyleExplicit
                         dataLayout:MPSGraphTensorNamedDataLayoutNCHW weightsLayout:MPSGraphTensorNamedDataLayoutOIHW];
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
        x = [graph_ transposeTensor:x dimension:1 withDimension:3 name:nil];   // N C W H
        x = [graph_ transposeTensor:x dimension:2 withDimension:3 name:nil];   // N C H W

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
                result = convolution(a, constant(k.data(), @[@12, @3, @2, @2], k.size()), 2, 0);
                break;
            }
            case AjmOp::Conv: {
                const size_t count = (size_t)op.o * op.i * op.k * op.k;
                MPSGraphTensor *weights = constant(model_.weights.data() + op.weight, @[@(op.o), @(op.i), @(op.k), @(op.k)], count);
                MPSGraphTensor *bias = constant(model_.weights.data() + op.bias, @[@1, @(op.o), @1, @1], (size_t)op.o);
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
                result = [graph_ concatTensors:parts dimension:1 name:nil];
                break;
            }
            case AjmOp::Shuffle:
                // out[c, y*r + dy, x*r + dx] = in[c*r*r + dy*r + dx, y, x]: the pixel-shuffle order.
                result = [graph_ depthToSpace2DTensor:a widthAxis:3 heightAxis:2 depthAxis:1 blockSize:(NSUInteger)op.factor
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
        y = [graph_ transposeTensor:y dimension:1 withDimension:2 name:nil];   // N H C W
        y = [graph_ transposeTensor:y dimension:2 withDimension:3 name:nil];   // N H W C
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
    AjmModel model_;
    id<MTLDevice> device_ = nil;
    id<MTLCommandQueue> queue_ = nil;
    MPSGraphDevice *graph_device_ = nil;
    MPSGraph *graph_ = nil;
    MPSGraphTensor *input_ = nil, *output_ = nil;
    MPSGraphExecutable *executable_ = nil;
    NSArray<NSNumber *> *in_shape_ = nil;
    std::vector<uint8_t> in_, out_;
};

} // namespace

std::unique_ptr<Executor> make_metal_executor(const ExecutorRequest &request)
{
    return std::make_unique<MetalExecutor>(request);
}

} // namespace aji
