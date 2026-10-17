#import <Foundation/Foundation.h>
#include "engine.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <thread>
#include <vector>
int main(int argc,char **argv) try {
    if(argc!=5){std::fprintf(stderr,"usage: probe MODELS MODEL CACHE OUTPUT\n");return 2;}
    @autoreleasepool {
        aji::ExecutorRequest request;request.provider="coremlnative";request.device="cpu";
        request.models_dir=argv[1];request.model=argv[2];request.cache_dir=argv[3];request.width=request.height=256;
        auto start=std::chrono::steady_clock::now();auto executor=aji::make_coreml_executor(request);
        double create=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        const std::string before=executor->placement_note();
        std::vector<uint8_t> input(256*256*3),output(512*512*3);
        for(size_t i=0;i<input.size();i++)input[i]=(uint8_t)((i*7+i/31)%256);
        aji::Job job;job.in=input.data();job.in_stride=256*3;job.out=output.data();job.out_stride=512*3;job.crop_w=job.crop_h=512;
        start=std::chrono::steady_clock::now();executor->run(job);
        double first=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        const std::string first_note=executor->placement_note();
        auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(10);
        std::string after=first_note;
        // Test-only observation after the measured first frame; never inserted
        // into configure, inference or the executor's destructor.
        while(after.rfind("pending",0)==0&&std::chrono::steady_clock::now()<deadline) {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));after=executor->placement_note();
        }
        std::ofstream file(argv[4],std::ios::binary);file.write((const char*)output.data(),output.size());aji::require(file.good(),"cannot write probe output");
        std::printf("executor_create_ms=%.3f\nfirst_process_ms=%.3f\nnote_before=%s\nnote_first=%s\nnote_after=%s\n",
            create,first,before.c_str(),first_note.c_str(),after.c_str());
        return 0;
    }
} catch(const std::exception &error){std::fprintf(stderr,"%s\n",error.what());return 1;}
