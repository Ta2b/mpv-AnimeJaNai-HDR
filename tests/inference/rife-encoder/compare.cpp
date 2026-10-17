// Targeted developer probe: no player, user config, cache or model is modified.
#include <NvInfer.h>
#include <cuda_runtime_api.h>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>

void check(bool ok,const char *message) {if(!ok)throw std::runtime_error(message);}
void cuda(cudaError_t code) {if(code!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(code));}
struct Logger:nvinfer1::ILogger {
 void log(Severity s,const char *text) noexcept override {if(s<=Severity::kWARNING)std::cerr<<text<<'\n';}
};
std::vector<char> read(const std::string &path) {
 std::ifstream file(path,std::ios::binary|std::ios::ate);check(bool(file),"cannot read input");
 auto size=file.tellg();check(size>0,"empty input");std::vector<char> bytes((size_t)size);file.seekg(0);file.read(bytes.data(),bytes.size());check(bool(file),"short read");return bytes;
}
struct Buffer {
 void *ptr=nullptr;size_t bytes;
 explicit Buffer(size_t n):bytes(n){cuda(cudaMalloc(&ptr,n));}
 ~Buffer(){cudaFree(ptr);}
 Buffer(const Buffer&)=delete;
};
struct Engine {
 std::unique_ptr<nvinfer1::ICudaEngine> engine;
 std::unique_ptr<nvinfer1::IExecutionContext> execution;
 Engine(nvinfer1::IRuntime &runtime,const std::string &path) {
  auto blob=read(path);engine.reset(runtime.deserializeCudaEngine(blob.data(),blob.size()));check(bool(engine),"deserialize engine");
  execution.reset(engine->createExecutionContext());check(bool(execution),"create context");
 }
 void bind(const char *name,Buffer &buffer) {
  const auto shape=execution->getTensorShape(name);check(shape.nbDims>0,"missing tensor");
  check(engine->getTensorDataType(name)==nvinfer1::DataType::kHALF,"expected FP16 boundary");
  size_t n=2;for(int i=0;i<shape.nbDims;++i){check(shape.d[i]>0,"unresolved tensor shape");n*=shape.d[i];}
  check(n==buffer.bytes,"tensor byte size mismatch");check(execution->setTensorAddress(name,buffer.ptr),"bind tensor");
 }
 void shape(const char *name,nvinfer1::Dims4 dimensions) {check(execution->setInputShape(name,dimensions),"set input shape");}
 void run(cudaStream_t stream){check(execution->enqueueV3(stream),"enqueue model");}
};
float half(uint16_t h) {
 unsigned sign=(h>>15)&1,exponent=(h>>10)&31,fraction=h&1023;
 if(exponent==31)return fraction?NAN:(sign?-INFINITY:INFINITY);
 float value=exponent?std::ldexp(float(1024+fraction),int(exponent)-25):std::ldexp(float(fraction),-24);
 return sign?-value:value;
}
int main(int argc,char **argv) try {
 check(argc==5||(argc==6&&std::string(argv[5])=="--timing"),"usage: compare reference.plan encoder.plan head.plan input.fp16 [--timing]");
 constexpr int H=768,W=1280;constexpr size_t pixels=size_t(H)*W;
 constexpr char feature[]="/encode/cnn3/ConvTranspose_output_0";
 Logger logger;std::unique_ptr<nvinfer1::IRuntime> runtime(nvinfer1::createInferRuntime(logger));check(bool(runtime),"create runtime");
 Engine reference(*runtime,argv[1]),encoder(*runtime,argv[2]),head(*runtime,argv[3]);
 auto input=read(argv[4]);check(input.size()==11*pixels*2,"bad input tensor size");
 Buffer in(input.size()),features(2*4*pixels*2),expected(3*pixels*2),candidate(3*pixels*2);
 cudaStream_t stream;cuda(cudaStreamCreate(&stream));
 reference.shape("input",{1,11,H,W});encoder.shape("input",{1,11,H,W});head.shape("input",{1,11,H,W});head.shape(feature,{2,4,H,W});
 reference.bind("input",in);reference.bind("output",expected);
 encoder.bind("input",in);encoder.bind(feature,features);
 head.bind("input",in);head.bind(feature,features);head.bind("output",candidate);
 cuda(cudaMemcpyAsync(in.ptr,input.data(),input.size(),cudaMemcpyHostToDevice,stream));
 encoder.run(stream);cuda(cudaStreamSynchronize(stream)); // one encoder for all phases
 std::vector<uint16_t> t(pixels),a(3*pixels),b(3*pixels);
 const uint16_t times[]={0x3400,0x3800,0x3a00};
 if(argc==5)for(int phase=0;phase<3;++phase) {
  std::fill(t.begin(),t.end(),times[phase]);
  cuda(cudaMemcpyAsync((char*)in.ptr+6*pixels*2,t.data(),pixels*2,cudaMemcpyHostToDevice,stream));
  reference.run(stream);head.run(stream);
  cuda(cudaMemcpyAsync(a.data(),expected.ptr,expected.bytes,cudaMemcpyDeviceToHost,stream));
  cuda(cudaMemcpyAsync(b.data(),candidate.ptr,candidate.bytes,cudaMemcpyDeviceToHost,stream));
  cuda(cudaStreamSynchronize(stream));
  size_t different=0,nonfinite=0;double max_abs=0,square=0;
  for(size_t i=0;i<a.size();++i) {
   different+=a[i]!=b[i];const double x=half(a[i]),y=half(b[i]);
   if(!std::isfinite(x)||!std::isfinite(y)){++nonfinite;continue;}
   const double delta=std::abs(x-y);max_abs=std::max(max_abs,delta);square+=delta*delta;
  }
  std::cout<<"{\"phase\":"<<((phase+1)*.25)<<",\"elements\":"<<a.size()<<",\"different_fp16\":"<<different
           <<",\"nonfinite\":"<<nonfinite<<",\"max_abs\":"<<max_abs<<",\"mse\":"<<square/a.size()<<"}"<<std::endl;
  // A mismatch is already a conclusion for strict Quality. Stop here; do not
  // time a numerically unqualified optimisation or mask it with a tolerance.
  if(different||nonfinite){cuda(cudaStreamDestroy(stream));return 2;}
 }
 if(argc==6) {
  // Same three inputs, tensors and device for both programs. Capture once to
  // match the runtime's graph route, then four bounded ABBA observations.
  std::vector<std::unique_ptr<Buffer>> inputs;
  for(int phase=0;phase<3;++phase) {
   inputs.emplace_back(new Buffer(in.bytes));
   std::fill(t.begin(),t.end(),times[phase]);
   cuda(cudaMemcpyAsync(inputs.back()->ptr,input.data(),in.bytes,cudaMemcpyHostToDevice,stream));
   cuda(cudaMemcpyAsync((char*)inputs.back()->ptr+6*pixels*2,t.data(),pixels*2,cudaMemcpyHostToDevice,stream));
   cuda(cudaStreamSynchronize(stream));
  }
  auto full=[&]{for(auto &data:inputs){reference.bind("input",*data);reference.run(stream);}};
  auto split=[&]{encoder.bind("input",*inputs[0]);encoder.run(stream);for(auto &data:inputs){head.bind("input",*data);head.run(stream);}};
  auto capture=[&](auto submit) {
   submit();cuda(cudaStreamSynchronize(stream)); // initialize TensorRT before capture
   cudaGraph_t graph;cudaGraphExec_t executable;
   cuda(cudaStreamBeginCapture(stream,cudaStreamCaptureModeGlobal));submit();
   cuda(cudaStreamEndCapture(stream,&graph));cuda(cudaGraphInstantiate(&executable,graph,0));
   cuda(cudaGraphDestroy(graph));return executable;
  };
  auto original=capture(full),derived=capture(split);
  cuda(cudaGraphLaunch(original,stream));cuda(cudaGraphLaunch(derived,stream));cuda(cudaStreamSynchronize(stream));
  cudaEvent_t begin,end;cuda(cudaEventCreate(&begin));cuda(cudaEventCreate(&end));
  for(int step=0;step<4;++step) {
   const bool baseline=step==0||step==3;
   cuda(cudaEventRecord(begin,stream));cuda(cudaGraphLaunch(baseline?original:derived,stream));
   cuda(cudaEventRecord(end,stream));cuda(cudaEventSynchronize(end));float ms=0;
   cuda(cudaEventElapsedTime(&ms,begin,end));
   std::cout<<"{\"step\":"<<step<<",\"program\":\""<<(baseline?"monolithic3":"encoder1-head3")<<"\",\"cuda_ms\":"<<ms<<"}"<<std::endl;
  }
  cuda(cudaMemcpyAsync(a.data(),expected.ptr,expected.bytes,cudaMemcpyDeviceToHost,stream));
  cuda(cudaMemcpyAsync(b.data(),candidate.ptr,candidate.bytes,cudaMemcpyDeviceToHost,stream));cuda(cudaStreamSynchronize(stream));
  check(a==b,"captured graph final-phase mismatch");
  cuda(cudaEventDestroy(begin));cuda(cudaEventDestroy(end));cuda(cudaGraphExecDestroy(original));cuda(cudaGraphExecDestroy(derived));
 }
 cuda(cudaStreamDestroy(stream));return 0;
} catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
