// Exhaust the finite FP16 source domain at the real shader's F32 boundary.
#include "span_resident.h"
#include <cstring>
#include <iostream>

int main() {
    ncnn::create_gpu_instance();
    if(ncnn::get_gpu_count()<1) {std::cerr<<"No Vulkan GPU\n";return 2;}
    const auto *device=ncnn::get_gpu_device(ncnn::get_default_gpu_index());
    {
        ncnn::Option opt;opt.use_fp16_storage=true;opt.use_fp16_packed=true;opt.use_fp16_arithmetic=true;
        AjiRifeWorkspace workspace(device);
        opt.blob_vkallocator=workspace.blob;opt.workspace_vkallocator=workspace.blob;opt.staging_vkallocator=workspace.staging;
        ncnn::Mat half(256,256,3,2u,1);
        for(int c=0;c<3;++c) {
            auto *p=(uint16_t*)half.channel(c);
            for(unsigned v=0;v<65536;++v)p[v]=(v&0x7c00)==0x7c00?0:(uint16_t)v;
        }
        ncnn::Mat expected;ncnn::cast_float16_to_float32(half,expected,opt);
        const float scale[3]={255,255,255},norm[3]={1.f/255,1.f/255,1.f/255};
        expected.substract_mean_normalize(nullptr,scale);expected.substract_mean_normalize(nullptr,norm);
        AjiSpanBoundary boundary(device);
        for(int storage:{32,16}) {
            ncnn::VkCompute command(device);std::vector<ncnn::VkMat> owners;ncnn::VkMat input;
            command.record_upload(half,input,opt);
            ncnn::Option next=opt;next.use_fp16_storage=next.use_fp16_packed=storage==16;
            auto result=boundary.record(input,command,next,owners);
            ncnn::Mat actual;command.record_download(result,actual,next);
            if(command.submit_and_wait()) {ncnn::vkDeviceWaitIdle(device->vkdevice());throw std::runtime_error("boundary submission failed");}
            ncnn::Mat reference=expected;
            if(storage==16) {ncnn::Mat rounded;ncnn::cast_float32_to_float16(expected,rounded,opt);ncnn::cast_float16_to_float32(rounded,reference,opt);}
            if(actual.w!=256||actual.h!=256||actual.c!=3||actual.elembits()!=32)throw std::runtime_error("invalid boundary output");
            size_t differences=0;
            for(int c=0;c<3;++c) {
                const float *a=actual.channel(c),*b=reference.channel(c);
                for(unsigned i=0;i<65536;++i)if(std::memcmp(a+i,b+i,4))++differences;
            }
            if(differences) {std::cerr<<"FAIL boundary storage="<<storage<<" differences="<<differences<<"\n";return 1;}
            std::cout<<"PASS boundary storage="<<storage<<": 196608 exact F32 values, finite FP16 domain, 255 then F32 1/255 preserved\n";
        }
    }
    ncnn::destroy_gpu_instance();
}
