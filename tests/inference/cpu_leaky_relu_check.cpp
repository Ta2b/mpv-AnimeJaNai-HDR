// One targeted boundary vector against independent ORT Less/Mul/Where kernels.
#include <onnxruntime_cxx_api.h>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>

int main(int argc,char **argv) {
    if (argc!=5) return 2;
    try {
        std::ifstream in(argv[4],std::ios::binary);
        std::vector<char> bytes((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
        if (bytes.empty() || bytes.size()%sizeof(float)) return 2;
        std::vector<float> data(bytes.size()/sizeof(float));std::memcpy(data.data(),bytes.data(),bytes.size());
        Ort::Env env(ORT_LOGGING_LEVEL_WARNING,"leaky-boundaries");
        Ort::SessionOptions reference_options,candidate_options;
        reference_options.SetGraphOptimizationLevel(ORT_ENABLE_ALL);
        candidate_options.SetGraphOptimizationLevel(ORT_ENABLE_ALL);
        candidate_options.RegisterCustomOpsLibrary(argv[3]);
        Ort::Session reference(env,argv[1],reference_options),candidate(env,argv[2],candidate_options);
        auto memory=Ort::MemoryInfo::CreateCpu(OrtArenaAllocator,OrtMemTypeDefault);
        const int64_t shape[]={(int64_t)data.size()};
        auto tensor=Ort::Value::CreateTensor<float>(memory,data.data(),data.size(),shape,1);
        const char *inputs[]={"input"},*outputs[]={"output"};
        auto a=reference.Run(Ort::RunOptions{nullptr},inputs,&tensor,1,outputs,1);
        auto b=candidate.Run(Ort::RunOptions{nullptr},inputs,&tensor,1,outputs,1);
        if (std::memcmp(a[0].GetTensorData<float>(),b[0].GetTensorData<float>(),bytes.size())) {
            for (size_t i=0;i<data.size();++i) {
                uint32_t x,y,z;std::memcpy(&x,&data[i],4);std::memcpy(&y,a[0].GetTensorData<float>()+i,4);std::memcpy(&z,b[0].GetTensorData<float>()+i,4);
                if (y!=z) std::cerr<<"index "<<std::dec<<i<<" input/ref/candidate "<<std::hex<<x<<' '<<y<<' '<<z<<'\n';
            }
            std::cerr<<"Operator boundary vector differs\n";return 1;
        }
        std::cout<<data.size()<<" FP32 boundary/near-boundary values: all bits identical to ORT Less/Mul/Where\n";
    }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
