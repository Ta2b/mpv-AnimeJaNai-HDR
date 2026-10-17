#import <Foundation/Foundation.h>
#include "engine.h"
#include <algorithm>
#include <fstream>
#include <vector>
int main(int argc,char **argv) try {
    if(argc!=6)return 2;
    @autoreleasepool {
        aji::ExecutorRequest r;r.provider="coremlnative";r.device="cpu";r.models_dir=argv[1];r.model=argv[2];r.cache_dir=argv[4];r.width=r.height=256;
        auto first=aji::make_coreml_executor(r);r.model=argv[3];r.width=r.height=512;auto second=aji::make_coreml_executor(r);
        const int pitch=256*3+16;std::vector<uint8_t> input(pitch*256);
        for(int y=0;y<256;++y)for(int x=0;x<256;++x)for(int k=0;k<3;++k)
            input[y*pitch+x*3+k]=(uint8_t)((x*3+y*2+k*30+(x/16%2)*60)%256);
        aji::Job j;j.in=input.data();j.in_stride=pitch;j.spread=true;
        auto held=first->run_resident(j);
        std::vector<uint8_t> before(512*512*3),after(before.size());
        aji::Job read;read.out=before.data();read.out_stride=512*3;read.crop_w=read.crop_h=512;read.spread=true;
        first->read_resident(*held,read);
        for(auto &v:input)v^=0xff;
        auto newer=first->run_resident(j); // Held output must not be overwritten.
        read.out=after.data();first->read_resident(*held,read);aji::require(before==after,"retained Core ML output was overwritten");newer.reset();
        // Invalid internal metadata must fail before prediction/readback.
        auto format=held->format;held->format=aji::ResidentImage::Format::RGB8NHWC;
        bool refused=false;try{second->run_resident(j,held.get());}catch(const std::exception &e){refused=std::string(e.what()).find("incompatible resident image")!=std::string::npos;}
        aji::require(refused,"invalid Core ML resident format accepted");held->format=format;
        auto final=second->run_resident(j,held.get());
        std::vector<uint8_t> output(1024*1024*3);read.out=output.data();read.out_stride=1024*3;read.crop_w=read.crop_h=1024;
        second->read_resident(*final,read);
        std::ofstream file(argv[5],std::ios::binary);file.write((const char*)output.data(),output.size());aji::require(file.good(),"cannot write owner probe output");
        std::printf("PASS retained-output-not-overwritten / invalid-format-refused / synchronous-recovery\n");
    }
} catch(const std::exception &error){std::fprintf(stderr,"%s\n",error.what());return 1;}
