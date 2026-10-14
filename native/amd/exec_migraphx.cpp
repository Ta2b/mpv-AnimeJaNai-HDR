// Native MIGraphX executor: no ORT partitioning or CPU inference fallback.
// The unchanged ONNX graph determines every tensor's precision. HIP handles
// RGB packing, RIFE grids, cropping and warping on the same explicit stream.
#include "engine.h"
#include "hip_kernels.h"
#include "device_model.h"
#include "onnx_flow.h"
#include <migraphx/migraphx.h>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <mutex>
#include <chrono>

namespace aji {
namespace {
void hip_check(hipError_t result, const char *operation) {
    require(result == hipSuccess, std::string(operation)+": "+hipGetErrorString(result));
}
void mig_check(migraphx_status result, const char *operation) {
    require(result == migraphx_status_success, std::string(operation)+": MIGraphX status "+std::to_string(result));
}
template<class T, migraphx_status (*Destroy)(T)> struct Handle {
    T value = nullptr;
    Handle() = default;
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    ~Handle() { reset(); }
    void reset() { if(value) Destroy(value); value=nullptr; }
    T *put() { reset(); return &value; }
    operator T() const { return value; }
};
using ProgramHandle=Handle<migraphx_program_t,migraphx_program_destroy>;
using ShapeHandle=Handle<migraphx_shape_t,migraphx_shape_destroy>;
using ArgumentHandle=Handle<migraphx_argument_t,migraphx_argument_destroy>;
using ParametersHandle=Handle<migraphx_program_parameters_t,migraphx_program_parameters_destroy>;
using ArgumentsHandle=Handle<migraphx_arguments_t,migraphx_arguments_destroy>;

struct Buffer {
    void *data=nullptr; size_t capacity=0;
    Buffer()=default; Buffer(const Buffer&)=delete;
    ~Buffer() { if(data) (void)hipFree(data); }
    void reserve(size_t bytes) {
        if(bytes<=capacity) return;
        void *next=nullptr; hip_check(hipMalloc(&next,bytes),"HIP allocation");
        if(data) (void)hipFree(data); data=next; capacity=bytes;
    }
    template<class T> T *as() const { return static_cast<T*>(data); }
};
struct Pinned {
    void *data=nullptr; size_t capacity=0;
    ~Pinned() { if(data) (void)hipHostFree(data); }
    void reserve(size_t bytes) {
        if(bytes<=capacity) return;
        void *next=nullptr;hip_check(hipHostMalloc(&next,bytes,hipHostMallocDefault),"HIP host allocation");
        if(data) (void)hipHostFree(data);data=next;capacity=bytes;
    }
};

// Read only GraphProto.input / ValueInfoProto.name. No model modification,
// graph execution or ORT session is needed to discover the input's name.
struct Proto {
    const uint8_t *p,*end;
    uint64_t number() {
        uint64_t v=0;
        for(int bits=0;bits<64;bits+=7) {
            require(p<end,"truncated ONNX varint");uint8_t c=*p++;
            if(bits==63) require(c<=1,"overflowed ONNX varint");
            v|=uint64_t(c&127)<<bits;if(!(c&128)) return v;
        }
        throw std::runtime_error("invalid ONNX varint");
    }
    bool field(unsigned &tag, Proto &body) {
        if(p==end) return false;
        const auto key=number();tag=(unsigned)(key>>3);const unsigned wire=key&7;
        require(tag!=0,"invalid ONNX field");
        size_t n=0;
        if(wire==0) { number();body={p,p};return true; }
        if(wire==1) n=8; else if(wire==5) n=4;
        else if(wire==2) { const auto size=number();require(size<=(uint64_t)(end-p),"truncated ONNX field");n=(size_t)size; }
        else throw std::runtime_error("unsupported ONNX wire type");
        require(n<=(size_t)(end-p),"truncated ONNX field");body={p,p+n};p+=n;return true;
    }
};
std::string input_name(const std::vector<char> &bytes) {
    require(!bytes.empty(),"empty ONNX model");
    Proto model{(const uint8_t*)bytes.data(),(const uint8_t*)bytes.data()+bytes.size()},body{};
    unsigned tag;
    while(model.field(tag,body)) if(tag==7) {
        Proto value{};
        while(body.field(tag,value)) if(tag==11) {
            Proto name{};
            while(value.field(tag,name)) if(tag==1) return std::string((const char*)name.p,(const char*)name.end);
        }
    }
    throw std::runtime_error("ONNX graph has no input");
}
struct Tensor {
    void *data=nullptr; int channels=0,w=0,h=0; bool half=false;
    size_t bytes=0;
};
Tensor tensor(const_migraphx_shape_t shape,void *data=nullptr) {
    const size_t *dims=nullptr,*strides=nullptr;size_t count=0,sc=0,bytes=0;
    migraphx_shape_datatype_t type;
    mig_check(migraphx_shape_lengths(&dims,&count,shape),"tensor lengths");
    mig_check(migraphx_shape_strides(&strides,&sc,shape),"tensor strides");
    mig_check(migraphx_shape_type(&type,shape),"tensor type");
    mig_check(migraphx_shape_bytes(&bytes,shape),"tensor bytes");
    require(count==4 && sc==4 && dims[0]==1,"MIGraphX needs batch-1 NCHW tensors");
    require(dims[1]>0 && dims[2]>0 && dims[3]>0 && dims[1]<=INT32_MAX && dims[2]<=INT32_MAX && dims[3]<=INT32_MAX,"invalid tensor dimensions");
    require(strides[3]==1 && strides[2]==dims[3]
        && (dims[1]==1 || strides[1]==dims[2]*dims[3]),"MIGraphX output must be contiguous NCHW");
    require(type==migraphx_shape_half_type || type==migraphx_shape_float_type,"MIGraphX model needs FP16 or FP32 tensors");
    const size_t element=type==migraphx_shape_half_type?2u:4u;
    require(dims[1]<=SIZE_MAX/(dims[2]*dims[3])/element,"MIGraphX tensor size overflow");
    require(bytes==dims[1]*dims[2]*dims[3]*element,
        "MIGraphX tensor size/type mismatch; install a runtime matching the build SDK");
    return {data,(int)dims[1],(int)dims[3],(int)dims[2],type==migraphx_shape_half_type,bytes};
}
int device_number(const std::string &device) {
    if(device.empty() || device=="gpu" || device=="GPU" || device=="auto") return 0;
    size_t read=0;const int id=std::stoi(device,&read);
    require(id>=0 && read==device.size(),"HIP device must be a nonnegative GPU index");return id;
}

class Model {
public:
    Model(const std::string &dir,const std::string &name,int w,int h,int channels,const std::string &device,
          hipStream_t external=nullptr,bool motion_only=false)
        : device_(device_number(device)),owns_stream_(!external),stream_(external) {
        activate();if(owns_stream_) hip_check(hipStreamCreateWithFlags(&stream_,hipStreamNonBlocking),"HIP stream");
        // Ensure cleanup of the stream even if graph parsing/compilation throws.
        try {
            const auto path=std::filesystem::u8path(dir)/std::filesystem::u8path(name+".onnx");
            std::ifstream file(path,std::ios::binary);
            require(file.good(),"cannot open ONNX model: "+path.u8string());
            std::vector<char> source((std::istreambuf_iterator<char>(file)),{}),motion;
            const std::string input=input_name(source);input_name_=input;
            Handle<migraphx_onnx_options_t,migraphx_onnx_options_destroy> parse;
            mig_check(migraphx_onnx_options_create(parse.put()),"ONNX options");
            size_t dims[4]={1,(size_t)channels,(size_t)h,(size_t)w};
            mig_check(migraphx_onnx_options_set_input_parameter_shape(parse,input.c_str(),dims,4),"ONNX fixed input");
            const bool flow_file=name.size()>=5 && name.compare(name.size()-5,5,".flow")==0;
            if(motion_only || flow_file) {
                std::string why;
                if(!aji_onnx_motion_outputs(source,&motion,&why)) {
                    require(!flow_file,"MIGraphX motion graph: "+why);
                    motion.clear(); // keep the unchanged RGB graph
                }
            }
            // Current models embed their weights. Parsing their bytes also
            // avoids narrow Windows file APIs for Unicode installation paths.
            const auto &graph=motion.empty()?source:motion;
            mig_check(migraphx_parse_onnx_buffer(program_.put(),graph.data(),graph.size(),parse),"MIGraphX ONNX parse");
            Handle<migraphx_target_t,migraphx_target_destroy> target;
            Handle<migraphx_compile_options_t,migraphx_compile_options_destroy> options;
            mig_check(migraphx_target_create(target.put(),"gpu"),"MIGraphX GPU target");
            mig_check(migraphx_compile_options_create(options.put()),"MIGraphX compile options");
            mig_check(migraphx_compile_options_set_offload_copy(options,false),"MIGraphX device I/O");
            mig_check(migraphx_compile_options_set_fast_math(options,false),"MIGraphX precise math");
            const char *tune=std::getenv("AJI_MIGRAPHX_TUNE");
            mig_check(migraphx_compile_options_set_exhaustive_tune_flag(options,!(tune && *tune=='0')),"MIGraphX kernel tuning");
            // Some library versions use process-global compiler/tuning caches.
            static std::mutex compile_mutex;
            { std::lock_guard<std::mutex> lock(compile_mutex);mig_check(migraphx_program_compile(program_,target,options),"MIGraphX compile"); }
            Handle<migraphx_program_parameter_shapes_t,migraphx_program_parameter_shapes_destroy> shapes;
            mig_check(migraphx_program_get_parameter_shapes(shapes.put(),program_),"MIGraphX parameters");
            size_t n=0;mig_check(migraphx_program_parameter_shapes_size(&n,shapes),"MIGraphX parameter count");
            std::vector<const char*> names(n);
            mig_check(migraphx_program_parameter_shapes_names(names.data(),shapes),"MIGraphX parameter names");
            mig_check(migraphx_program_parameters_create(parameters_.put()),"MIGraphX bindings");
            bool found=false;
            for(const char *param:names) {
                const_migraphx_shape_t shape=nullptr;
                mig_check(migraphx_program_parameter_shapes_get(&shape,shapes,param),"MIGraphX parameter shape");
                size_t bytes=0;mig_check(migraphx_shape_bytes(&bytes,shape),"MIGraphX parameter size");
                auto memory=std::make_unique<Buffer>();memory->reserve(bytes);
                hip_check(hipMemsetAsync(memory->data,0,bytes,stream_),"HIP parameter initialization");
                ArgumentHandle argument;
                mig_check(migraphx_argument_create(argument.put(),shape,memory->as<char>()),"MIGraphX device argument");
                mig_check(migraphx_program_parameters_add(parameters_,param,argument),"MIGraphX bind parameter");
                if(input==param) { input_=tensor(shape,memory->data);found=true; }
                else {
                    const std::string parameter=param;
                    const auto marker=parameter.find(":#output_");
                    require(parameter=="scratch" || marker!=std::string::npos,
                        "unexpected additional model input: "+parameter);
                    if(marker!=std::string::npos && parameter.substr(marker)==":#output_0") output_name_=parameter;
                }
                buffers_.push_back(std::move(memory));
            }
            require(found && input_.channels==channels && input_.w==w && input_.h==h,"MIGraphX fixed input shape mismatch");
            Handle<migraphx_shapes_t,migraphx_shapes_destroy> out_shapes;
            mig_check(migraphx_program_get_output_shapes(out_shapes.put(),program_),"MIGraphX output shapes");
            size_t out_count=0;mig_check(migraphx_shapes_size(&out_count,out_shapes),"MIGraphX output shape count");
            for(size_t i=0;i<out_count;++i) {
                const_migraphx_shape_t shape=nullptr;mig_check(migraphx_shapes_get(&shape,out_shapes,i),"MIGraphX output shape");
                shape_outputs_.push_back(tensor(shape));
            }
            hip_check(hipStreamSynchronize(stream_),"HIP initialization");
            hipDeviceProp_t properties{};hip_check(hipGetDeviceProperties(&properties,device_),"HIP GPU properties");
            label=std::string("MIGraphX + HIP / ")+properties.name;
        } catch(...) {
            (void)hipStreamSynchronize(stream_);results_.reset();parameters_.reset();program_.reset();
            if(owns_stream_) (void)hipStreamDestroy(stream_);stream_=nullptr;throw;
        }
    }
    ~Model() {
        quiesce();
        invalidate_graph();
        results_.reset();parameters_.reset();program_.reset();
        if(profile_start_) (void)hipEventDestroy(profile_start_);
        if(profile_end_) (void)hipEventDestroy(profile_end_);
        if(output_start_) (void)hipEventDestroy(output_start_);
        if(output_end_) (void)hipEventDestroy(output_end_);
        if(stream_ && owns_stream_) (void)hipStreamDestroy(stream_);
        if(capture_stream_) (void)hipStreamDestroy(capture_stream_);
    }
    void quiesce() noexcept { (void)hipSetDevice(device_);if(stream_) (void)hipStreamSynchronize(stream_); }
    void activate() { hip_check(hipSetDevice(device_),"HIP select GPU"); }
    void synchronize() { hip_check(hipStreamSynchronize(stream_),"HIP frame completion"); }
    const Tensor &input() const { return input_; }
    const std::vector<Tensor> &output_shapes() const { return shape_outputs_; }
    void external_input(const void *pointer) {
        if(pointer==input_.data) return;
        invalidate_graph();
        bind_external(input_name_,input_,const_cast<void*>(pointer));input_.data=const_cast<void*>(pointer);
    }
    bool external_output(void *pointer) {
        if(!pointer || output_name_.empty()) return false;
        if(pointer==output_pointer_) return true;
        invalidate_graph();
        bind_external(output_name_,shape_outputs_.front(),pointer);output_pointer_=pointer;return true;
    }
    hipStream_t stream() const { return stream_; }
    void enable_profiling() {
        hip_check(hipEventCreate(&profile_start_),"HIP profiling event");
        try { hip_check(hipEventCreate(&profile_end_),"HIP profiling event"); }
        catch(...) { (void)hipEventDestroy(profile_start_);profile_start_=nullptr;throw; }
        hip_check(hipEventCreate(&output_start_),"HIP output profiling event");
        hip_check(hipEventCreate(&output_end_),"HIP output profiling event");
    }
    double measured_inference() {
        if(!profile_pending_) return 0;
        float ms=0;hip_check(hipEventElapsedTime(&ms,profile_start_,profile_end_),"HIP inference timing");
        profile_pending_=false;return ms;
    }
    void begin_output() {
        if(output_start_ && !output_open_) {
            hip_check(hipEventRecord(output_start_,stream_),"HIP output start");output_open_=true;
        }
    }
    void end_output() {
        if(output_end_ && output_open_) {
            hip_check(hipEventRecord(output_end_,stream_),"HIP output end");output_open_=false;output_pending_=true;
        }
    }
    double measured_output() {
        if(!output_pending_) return 0;
        float ms=0;hip_check(hipEventElapsedTime(&ms,output_start_,output_end_),"HIP output timing");
        output_pending_=false;return ms;
    }
    const std::vector<Tensor> &run() {
        // The host bridge drains each call before another run. Keep the returned
        // arguments alive while HIP kernels consume their device buffers.
        if(profile_start_) hip_check(hipEventRecord(profile_start_,stream_),"HIP inference start");
        if(graph_) {
            if(hipGraphLaunch(graph_,stream_)==hipSuccess) {
                if(profile_end_) { hip_check(hipEventRecord(profile_end_,stream_),"HIP inference end");profile_pending_=true; }
                return outputs_;
            }
            invalidate_graph();graph_ok_=false;(void)hipGetLastError();
        }
        mig_check(migraphx_program_run_async(results_.put(),program_,parameters_,stream_,"ihipStream_t"),"MIGraphX device inference");
        if(profile_end_) { hip_check(hipEventRecord(profile_end_,stream_),"HIP inference end");profile_pending_=true; }
        size_t n=0;mig_check(migraphx_arguments_size(&n,results_),"MIGraphX output count");
        outputs_.clear();outputs_.reserve(n);
        for(size_t i=0;i<n;++i) {
            const_migraphx_argument_t arg=nullptr;const_migraphx_shape_t shape=nullptr;char *ptr=nullptr;
            mig_check(migraphx_arguments_get(&arg,results_,i),"MIGraphX output");
            mig_check(migraphx_argument_shape(&shape,arg),"MIGraphX output shape");
            mig_check(migraphx_argument_buffer(&ptr,arg),"MIGraphX output buffer");
            outputs_.push_back(tensor(shape,ptr));
        }
        capture_graph();
        return outputs_;
    }
    std::string label;
private:
    void invalidate_graph() noexcept {
        if(graph_) { (void)hipGraphExecDestroy(graph_);graph_=nullptr; }
        captured_results_.reset();
    }
    void capture_graph() {
        const char *enabled=std::getenv("AJI_MIGRAPHX_GRAPH");
        if(!graph_ok_ || (enabled && *enabled=='0')) return;
        // Warmup already produced this frame. Capture on a separate stream
        // and retain both argument sets: recording must never free its output.
        synchronize();
        bool ok=true;
        if(!capture_stream_) ok=hipStreamCreateWithFlags(&capture_stream_,hipStreamNonBlocking)==hipSuccess;
        hipGraph_t captured=nullptr;
        if(ok) {
            ok=hipStreamBeginCapture(capture_stream_,hipStreamCaptureModeThreadLocal)==hipSuccess;
            if(ok) {
                const auto ran=migraphx_program_run_async(captured_results_.put(),program_,parameters_,capture_stream_,"ihipStream_t");
                const auto ended=hipStreamEndCapture(capture_stream_,&captured);
                ok=ran==migraphx_status_success && ended==hipSuccess && captured;
            }
        }
        // Only replay a graph whose outputs have exactly the persistent
        // addresses and layouts returned by the warmup; allocators that create
        // a new output per eval stay on the ordinary path.
        if(ok) {
            size_t count=0;ok=migraphx_arguments_size(&count,captured_results_)==migraphx_status_success && count==outputs_.size();
            for(size_t i=0;ok && i<count;++i) {
                const_migraphx_argument_t argument=nullptr;const_migraphx_shape_t shape=nullptr;char *pointer=nullptr;
                ok=migraphx_arguments_get(&argument,captured_results_,i)==migraphx_status_success
                   && migraphx_argument_shape(&shape,argument)==migraphx_status_success
                   && migraphx_argument_buffer(&pointer,argument)==migraphx_status_success;
                if(ok) {
                    try {
                        const auto view=tensor(shape,pointer);const auto &old=outputs_[i];
                        ok=view.data==old.data && view.w==old.w && view.h==old.h && view.channels==old.channels && view.half==old.half;
                    } catch(...) { ok=false; }
                }
            }
        }
        if(ok) ok=hipGraphInstantiate(&graph_,captured,nullptr,nullptr,0)==hipSuccess;
        if(captured) (void)hipGraphDestroy(captured);
        if(!ok) {
            invalidate_graph();graph_ok_=false;(void)hipGetLastError();
        }
    }
    void bind_external(const std::string &name,const Tensor &t,void *pointer) {
        size_t dims[4]={1,(size_t)t.channels,(size_t)t.h,(size_t)t.w};
        ShapeHandle shape;
        mig_check(migraphx_shape_create(shape.put(),t.half?migraphx_shape_half_type:migraphx_shape_float_type,dims,4),"MIGraphX external shape");
        ArgumentHandle argument;
        mig_check(migraphx_argument_create(argument.put(),shape,(char*)pointer),"MIGraphX external argument");
        mig_check(migraphx_program_parameters_add(parameters_,name.c_str(),argument),"MIGraphX external binding");
    }

    int device_;bool owns_stream_;hipStream_t stream_=nullptr;Tensor input_;
    ProgramHandle program_;std::vector<std::unique_ptr<Buffer>> buffers_;
    ParametersHandle parameters_;ArgumentsHandle results_;std::vector<Tensor> outputs_,shape_outputs_;
    std::string input_name_,output_name_;void *output_pointer_=nullptr;
    hipEvent_t profile_start_=nullptr,profile_end_=nullptr;bool profile_pending_=false;
    hipEvent_t output_start_=nullptr,output_end_=nullptr;bool output_open_=false,output_pending_=false;
    hipGraphExec_t graph_=nullptr;hipStream_t capture_stream_=nullptr;bool graph_ok_=true;
    ArgumentsHandle captured_results_;
};
void upload(Buffer &dst,const uint8_t *src,ptrdiff_t stride,int w,int h,hipStream_t stream) {
    require(src && stride>=(ptrdiff_t)w*3,"invalid RGB input stride");
    dst.reserve((size_t)w*h*3);
    hip_check(hipMemcpy2DAsync(dst.data,(size_t)w*3,src,(size_t)stride,(size_t)w*3,h,hipMemcpyHostToDevice,stream),"HIP RGB upload");
}
void download(Model &model,Buffer &gpu,Pinned &host,uint8_t *out,ptrdiff_t stride,int w,int h) {
    require(out && stride>=(ptrdiff_t)w*3,"invalid RGB output stride");
    const size_t bytes=(size_t)w*h*3;host.reserve(bytes);
    hip_check(hipMemcpyAsync(host.data,gpu.data,bytes,hipMemcpyDeviceToHost,model.stream()),"HIP RGB download");
    model.end_output();
    model.synchronize();
    for(int y=0;y<h;++y) std::memcpy(out+(ptrdiff_t)y*stride,(uint8_t*)host.data+(size_t)y*w*3,(size_t)w*3);
}

class MigExecutor final:public Executor {
public:
    explicit MigExecutor(const ExecutorRequest &r):model_(r.models_dir,r.model,r.width,r.height,3,r.device) { label=model_.label; }
    void run(const Job &job) override {
        model_.activate();const auto &in=model_.input();auto stream=model_.stream();
        upload(rgb_,job.in,job.in_stride,in.w,in.h,stream);
        hip_check(amd::pack_rgb(rgb_.as<uint8_t>(),in.data,in.half,in.w,in.h,in.w,in.h,0,0,stream),"HIP SPAN input");
        const auto &outs=model_.run();require(outs.size()==1 && outs[0].channels==3,"SPAN must have one RGB output");
        const auto &out=outs[0];
        require(out.w==2*in.w && out.h==2*in.h,"SPAN must upscale by two");
        require(job.crop_x>=0 && job.crop_y>=0 && job.crop_w>0 && job.crop_h>0
            && job.crop_x+job.crop_w<=out.w && job.crop_y+job.crop_h<=out.h,"invalid SPAN output crop");
        output_.reserve((size_t)job.crop_w*job.crop_h*3);
        hip_check(amd::unpack_rgb(out.data,out.half,output_.as<uint8_t>(),out.w,out.h,job.crop_x,job.crop_y,job.crop_w,job.crop_h,stream),"HIP SPAN output");
        download(model_,output_,host_,job.out,job.out_stride,job.crop_w,job.crop_h);
    }
    ~MigExecutor() override { model_.quiesce(); }
private:
    Model model_;Buffer rgb_,output_;Pinned host_;
};

class MigInterpolator final:public Interpolator {
public:
    explicit MigInterpolator(const InterpolatorRequest &r):
        w_(r.width),h_(r.height),pw_((w_+63)/64*64),ph_((h_+63)/64*64),
        left_(((pw_-w_)/2)&~1),top_(((ph_-h_)/2)&~1),
        model_(r.models_dir,r.model,pw_,ph_,11,r.device),profile_(r.profile) {
        label=model_.label;
        if(profile_) model_.enable_profiling();
        for(auto &v:kept_) v.resize((size_t)w_*h_*3);
        hip_check(amd::rife_grid(model_.input().data,model_.input().half,pw_,ph_,model_.stream()),"HIP RIFE grid");
        model_.synchronize();
        moving_=r.model.size()>=5 && r.model.compare(r.model.size()-5,5,".flow")==0;
    }
    ~MigInterpolator() override { model_.quiesce(); }
    bool has_motion() const override { return moving_; }
    void estimate(const uint8_t *a,ptrdiff_t as,const uint8_t *b,ptrdiff_t bs,double t) {
        require(moving_,"RIFE model has no flow outputs");prepare(a,as,b,bs,t);
        const auto &outs=model_.run();require(outs.size()==2,"RIFE motion graph needs flow and mask outputs");
        model_.begin_output();
        const Tensor *f=nullptr,*m=nullptr;
        for(const auto &v:outs) { if(v.channels==4) f=&v;if(v.channels==1) m=&v; }
        require(f && m && f->w==pw_ && f->h==ph_ && m->w==pw_ && m->h==ph_,"invalid RIFE flow/mask geometry");
        const size_t area=(size_t)w_*h_;
        flow_.reserve(4*area*sizeof(float));mask_.reserve(area*sizeof(float));
        hip_check(amd::crop_planes(f->data,f->half,flow_.as<float>(),4,pw_,ph_,left_,top_,w_,h_,model_.stream()),"HIP flow crop");
        hip_check(amd::crop_planes(m->data,m->half,mask_.as<float>(),1,pw_,ph_,left_,top_,w_,h_,model_.stream()),"HIP mask crop");
        have_motion_=true;++timing.runs;
    }
    bool device_motion(const uint8_t *a,ptrdiff_t as,const uint8_t *b,ptrdiff_t bs,double t,float *largest) override {
        estimate(a,as,b,bs,t);
        if(!largest) return true; // no host decision needed for another instant of this pair
        maximum_.reserve(sizeof(unsigned int));host_maximum_.reserve(sizeof(unsigned int));
        hip_check(hipMemsetAsync(maximum_.data,0,sizeof(unsigned int),model_.stream()),"HIP flow maximum reset");
        hip_check(amd::flow_max(flow_.as<float>(),4*(size_t)w_*h_,maximum_.as<unsigned int>(),model_.stream()),"HIP flow maximum");
        hip_check(hipMemcpyAsync(host_maximum_.data,maximum_.data,sizeof(unsigned int),hipMemcpyDeviceToHost,model_.stream()),"HIP flow maximum readback");
        model_.end_output();model_.synchronize();collect_inference();std::memcpy(largest,host_maximum_.data,sizeof(float));return true;
    }
    void motion(const uint8_t *a,ptrdiff_t as,const uint8_t *b,ptrdiff_t bs,double t,
                std::vector<float> &flow,std::vector<float> &mask) override {
        estimate(a,as,b,bs,t);const size_t area=(size_t)w_*h_;
        // Only the pair decision needs host flow. The device copy survives for
        // every warped instant; no flow or mask is uploaded again by warp().
        host_motion_.reserve(5*area*sizeof(float));
        hip_check(hipMemcpyAsync(host_motion_.data,flow_.data,4*area*sizeof(float),hipMemcpyDeviceToHost,model_.stream()),"HIP flow readback");
        hip_check(hipMemcpyAsync((float*)host_motion_.data+4*area,mask_.data,area*sizeof(float),hipMemcpyDeviceToHost,model_.stream()),"HIP mask readback");
        model_.end_output();model_.synchronize();collect_inference();flow.resize(4*area);mask.resize(area);
        std::memcpy(flow.data(),host_motion_.data,4*area*sizeof(float));
        std::memcpy(mask.data(),(float*)host_motion_.data+4*area,area*sizeof(float));
    }
    bool warp(const uint8_t *a,const uint8_t *b,int w,int h,uint64_t aid,uint64_t bid,
              float t,bool derived,uint8_t *out,ptrdiff_t stride) override {
        require(have_motion_,"HIP warp requires a motion estimate");model_.activate();
        model_.begin_output();
        // Content identities come from the core's exact endpoint cache.
        if(up_w_!=w || up_h_!=h) { up_ids_[0]=up_ids_[1]=0;up_w_=w;up_h_=h; }
        const uint64_t ids[2]={aid,bid};const uint8_t *pictures[2]={a,b};
        if(up_ids_[1]==aid && up_ids_[0]!=aid) { std::swap(up_[0],up_[1]);std::swap(up_ids_[0],up_ids_[1]); }
        for(int i=0;i<2;++i) if(up_ids_[i]!=ids[i]) {
            if(!up_[i]) up_[i]=std::make_unique<Buffer>();
            upload(*up_[i],pictures[i],(ptrdiff_t)w*3,w,h,model_.stream());up_ids_[i]=ids[i];
        }
        output_.reserve((size_t)w*h*3);
        hip_check(amd::warp_rgb(up_[0]->as<uint8_t>(),up_[1]->as<uint8_t>(),output_.as<uint8_t>(),w,h,
            flow_.as<float>(),mask_.as<float>(),w_,h_,t,derived,model_.stream()),"HIP RIFE warp");
        download(model_,output_,host_output_,out,stride,w,h);collect_inference();return true;
    }
    void run(const uint8_t *a,ptrdiff_t as,const uint8_t *b,ptrdiff_t bs,double t,
             uint8_t *out,ptrdiff_t stride) override {
        prepare(a,as,b,bs,t);const auto &outs=model_.run();
        model_.begin_output();
        require(!outs.empty() && outs[0].channels==3 && outs[0].w==pw_ && outs[0].h==ph_,"invalid RIFE RGB output");
        output_.reserve((size_t)w_*h_*3);
        hip_check(amd::unpack_rgb(outs[0].data,outs[0].half,output_.as<uint8_t>(),pw_,ph_,left_,top_,w_,h_,model_.stream()),"HIP RIFE output");
        download(model_,output_,host_output_,out,stride,w_,h_);collect_inference();++timing.runs;
    }
private:
    void collect_inference() {
        if(profile_) { timing.inference_ms+=model_.measured_inference();timing.output_ms+=model_.measured_output(); }
    }
    bool same(const uint8_t *p,ptrdiff_t stride,int slot) {
        if(!have_[slot]) return false;
        for(int y=0;y<h_;++y) if(std::memcmp(kept_[slot].data()+(size_t)y*w_*3,p+(ptrdiff_t)y*stride,(size_t)w_*3)) return false;
        return true;
    }
    void prepare(const uint8_t *a,ptrdiff_t as,const uint8_t *b,ptrdiff_t bs,double t) {
        const auto started=std::chrono::steady_clock::now();
        model_.activate();require(t>0 && t<1,"invalid RIFE instant");
        const auto &in=model_.input();const size_t plane=(size_t)pw_*ph_,elem=in.half?2:4;
        if(!same(a,as,0) && same(a,as,1)) {
            hip_check(hipMemcpyAsync(in.data,(char*)in.data+3*plane*elem,3*plane*elem,hipMemcpyDeviceToDevice,model_.stream()),"HIP endpoint promotion");
            std::swap(kept_[0],kept_[1]);have_[0]=true;have_[1]=false;++timing.source_promotions;
        }
        const uint8_t *pixels[2]={a,b};const ptrdiff_t strides[2]={as,bs};
        for(int i=0;i<2;++i) {
            if(same(pixels[i],strides[i],i)) { ++timing.source_hits;continue; }
            upload(raw_[i],pixels[i],strides[i],w_,h_,model_.stream());
            hip_check(amd::pack_rgb(raw_[i].as<uint8_t>(),(char*)in.data+i*3*plane*elem,in.half,w_,h_,pw_,ph_,left_,top_,model_.stream()),"HIP RIFE input");
            for(int y=0;y<h_;++y) std::memcpy(kept_[i].data()+(size_t)y*w_*3,pixels[i]+(ptrdiff_t)y*strides[i],(size_t)w_*3);
            have_[i]=true;++timing.source_preparations;
        }
        const float instant=(float)t;
        if(!have_time_ || instant!=time_) {
            hip_check(amd::timestep(in.data,in.half,pw_,ph_,instant,model_.stream()),"HIP RIFE instant");
            time_=instant;have_time_=true;++timing.timestep_updates;
        }
        if(profile_) timing.preparation_ms+=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();
    }
    int w_,h_,pw_,ph_,left_,top_;Model model_;
    Buffer raw_[2],output_,flow_,mask_,maximum_;Pinned host_output_,host_motion_,host_maximum_;
    std::vector<uint8_t> kept_[2];bool have_[2]={false,false};
    bool moving_=false,have_motion_=false,have_time_=false;float time_=0;
    bool profile_=false;
    std::unique_ptr<Buffer> up_[2];uint64_t up_ids_[2]={0,0};int up_w_=0,up_h_=0;
};
}
std::unique_ptr<Executor> make_migraphx_executor(const ExecutorRequest &r) { return std::make_unique<MigExecutor>(r); }
std::unique_ptr<Interpolator> make_migraphx_interpolator(const InterpolatorRequest &r) { return std::make_unique<MigInterpolator>(r); }
namespace amd {
namespace {
DeviceTensor view(const Tensor &v) { return {v.data,v.channels,v.w,v.h,v.half}; }
class NativeDeviceModel final:public DeviceModel {
public:
    NativeDeviceModel(const std::string &path,int w,int h,int channels,int device,hipStream_t stream,bool motion_only)
        : model_(std::filesystem::u8path(path).parent_path().u8string(),std::filesystem::u8path(path).stem().u8string(),
                 w,h,channels,std::to_string(device),stream,motion_only) {}
    DeviceTensor input() const override { return view(model_.input()); }
    std::vector<DeviceTensor> output_shapes() const override {
        std::vector<DeviceTensor> shapes;for(const auto &v:model_.output_shapes()) shapes.push_back(view(v));return shapes;
    }
    std::vector<DeviceTensor> enqueue(const void *input,void *output) override {
        model_.activate();
        model_.external_input(input);
        // Some optimized graphs alias an output instead of exposing a writable
        // output parameter. The caller then uses the returned device pointer.
        model_.external_output(output);
        std::vector<DeviceTensor> out;for(const auto &v:model_.run()) out.push_back(view(v));return out;
    }
private:
    Model model_;
};
}
std::unique_ptr<DeviceModel> make_device_model(const std::string &path,int w,int h,int channels,int device,hipStream_t stream,bool motion_only) {
    return std::make_unique<NativeDeviceModel>(path,w,h,channels,device,stream,motion_only);
}
}
}
