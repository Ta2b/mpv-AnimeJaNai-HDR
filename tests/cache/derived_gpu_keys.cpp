// Fixture-only: seed trusted reference plans under observed candidate keys.
#include "model_identity.h"
#include <cuda_runtime_api.h>
#include <iostream>
int main(int argc,char **argv)
{
    try {
        if(argc!=4)return 2;
        int device=0,runtime=0,driver=0;cudaDeviceProp prop{};
        if(cudaGetDevice(&device)!=cudaSuccess || cudaGetDeviceProperties(&prop,device)!=cudaSuccess
            || cudaRuntimeGetVersion(&runtime)!=cudaSuccess || cudaDriverGetVersion(&driver)!=cudaSuccess)return 3;
        std::string uuid;const char *digits="0123456789abcdef";
        for(unsigned char byte:prop.uuid.bytes){uuid+=digits[byte>>4];uuid+=digits[byte&15];}
        const auto gpu=std::string(prop.name)+"-sm"+std::to_string(prop.major)+"."+std::to_string(prop.minor)+"-"+uuid;
        const auto version=std::string(argv[3])+"-cuda"+std::to_string(runtime)+"-driver"+std::to_string(driver);
        const auto cache=std::filesystem::u8path(argv[2]);
        const auto source=aji::cache::freeze_model(std::filesystem::u8path(argv[1]),cache/".aji-sources-v2");
        const auto motion=aji::cache::freeze_motion_model(source,cache/".aji-motion-v3");
        const std::string settings="--stronglyTyped --optShapes=input:1x11x128x128"
            " --inputIOFormats=fp16:chw --outputIOFormats=fp16:chw"
            " --tacticSources=-CUDNN,-CUBLAS,-CUBLAS_LT --skipInference";
        std::cout<<aji::cache::engine_name(source.content,settings,version,gpu,"",source.scheme)<<'\n'
            <<aji::cache::engine_name(motion.content,settings,version,gpu,"",motion.scheme)<<'\n'
            <<version<<'\n'<<gpu<<'\n';
    }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
