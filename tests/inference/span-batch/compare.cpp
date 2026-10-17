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
 void bind(const char *name,void *address,size_t bytes) {
  const auto shape=execution->getTensorShape(name);check(shape.nbDims>0,"missing tensor");
  check(engine->getTensorDataType(name)==nvinfer1::DataType::kHALF,"expected FP16 boundary");
  size_t n=2;for(int i=0;i<shape.nbDims;++i){check(shape.d[i]>0,"unresolved tensor shape");n*=shape.d[i];}
  check(n==bytes,"tensor byte size mismatch");check(execution->setTensorAddress(name,address),"bind tensor");
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
 check(argc==4,"usage: compare reference.plan batch.plan input4.fp16");
 constexpr int H=720,W=1280;constexpr size_t input_bytes=size_t(3)*H*W*2,output_bytes=size_t(3)*H*W*4*2;
 Logger logger;std::unique_ptr<nvinfer1::IRuntime> runtime(nvinfer1::createInferRuntime(logger));check(bool(runtime),"runtime");
 Engine reference(*runtime,argv[1]),batch(*runtime,argv[2]);
 reference.shape("input",{1,3,H,W});batch.shape("input",{4,3,H,W});
 auto input=read(argv[3]);check(input.size()==4*input_bytes,"four input tensors required");
 Buffer in(input.size()),a(4*output_bytes),b(4*output_bytes);cudaStream_t stream;cuda(cudaStreamCreate(&stream));
 cuda(cudaMemcpyAsync(in.ptr,input.data(),input.size(),cudaMemcpyHostToDevice,stream));cuda(cudaStreamSynchronize(stream));
 auto sequential=[&]{for(int i=0;i<4;i++) {
  reference.bind("input",(char*)in.ptr+i*input_bytes,input_bytes);
  reference.bind("output",(char*)a.ptr+i*output_bytes,output_bytes);reference.run(stream);
 }};
 batch.bind("input",in.ptr,in.bytes);batch.bind("output",b.ptr,b.bytes);
 auto together=[&]{batch.run(stream);};
 sequential();together();cuda(cudaStreamSynchronize(stream));
 std::vector<uint16_t> old(4*output_bytes/2),now(old.size());
 cuda(cudaMemcpy(old.data(),a.ptr,a.bytes,cudaMemcpyDeviceToHost));cuda(cudaMemcpy(now.data(),b.ptr,b.bytes,cudaMemcpyDeviceToHost));
 for(int frame=0;frame<4;frame++) {
  size_t different=0,nonfinite=0;double max_abs=0,square=0;const size_t count=output_bytes/2;
  for(size_t p=0;p<count;p++) {
   size_t i=frame*count+p;different+=old[i]!=now[i];double x=half(old[i]),y=half(now[i]);
   if(!std::isfinite(x)||!std::isfinite(y)){++nonfinite;continue;}
   double delta=std::abs(x-y);max_abs=std::max(max_abs,delta);square+=delta*delta;
  }
  std::cout<<"{\"frame\":"<<frame<<",\"elements\":"<<count<<",\"different_fp16\":"<<different<<",\"nonfinite\":"<<nonfinite<<",\"max_abs\":"<<max_abs<<",\"mse\":"<<square/count<<"}"<<std::endl;
  if(different||nonfinite){cuda(cudaStreamDestroy(stream));return 2;}
 }
 auto capture=[&](auto run) {cudaGraph_t graph;cudaGraphExec_t executable;
  cuda(cudaStreamBeginCapture(stream,cudaStreamCaptureModeGlobal));run();cuda(cudaStreamEndCapture(stream,&graph));
  cuda(cudaGraphInstantiate(&executable,graph,0));cuda(cudaGraphDestroy(graph));return executable;};
 auto one=capture(sequential),four=capture(together);
 cuda(cudaGraphLaunch(one,stream));cuda(cudaGraphLaunch(four,stream));cuda(cudaStreamSynchronize(stream));
 cudaEvent_t begin,end;cuda(cudaEventCreate(&begin));cuda(cudaEventCreate(&end));
 for(int i=0;i<4;i++) {
  bool baseline=i==0||i==3;cuda(cudaEventRecord(begin,stream));cuda(cudaGraphLaunch(baseline?one:four,stream));
  cuda(cudaEventRecord(end,stream));cuda(cudaEventSynchronize(end));float ms=0;cuda(cudaEventElapsedTime(&ms,begin,end));
  std::cout<<"{\"step\":"<<i<<",\"program\":\""<<(baseline?"four-B1":"one-B4")<<"\",\"cuda_ms\":"<<ms<<"}"<<std::endl;
 }
 std::cout<<"{\"reference_context_bytes\":"<<reference.engine->getDeviceMemorySizeV2()<<",\"batch_context_bytes\":"<<batch.engine->getDeviceMemorySizeV2()<<",\"input_bytes\":"<<in.bytes<<",\"output_bytes\":"<<b.bytes<<"}"<<std::endl;
 cuda(cudaMemcpy(old.data(),a.ptr,a.bytes,cudaMemcpyDeviceToHost));cuda(cudaMemcpy(now.data(),b.ptr,b.bytes,cudaMemcpyDeviceToHost));
 check(old==now,"captured batch output mismatch");
 cuda(cudaEventDestroy(begin));cuda(cudaEventDestroy(end));cuda(cudaGraphExecDestroy(one));cuda(cudaGraphExecDestroy(four));
 cuda(cudaStreamDestroy(stream));return 0;
} catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
