#pragma once
#include "net.h"
#include "command.h"
#include "pipeline.h"
#include "rife_frame_cache.h"
#include <memory>
#include <stdexcept>

// Internal, synchronous SPAN workspace. Host ABI and model precision unchanged.
// The bridge's F32 download -> *255 -> *float(1/255) -> upload is reproduced on
// device, including both rounded F32 products and the next upload's storage cast.
class AjiSpanBoundary {
public:
    explicit AjiSpanBoundary(const ncnn::VulkanDevice *device,int gpu_index=-1) : device_(device) {
        ncnn::Option fp32;fp32.vulkan_device_index=gpu_index;
        fp32.use_fp16_packed=false;fp32.use_fp16_storage=false;fp32.use_fp16_arithmetic=false;
        const char shader[]=R"glsl(#version 450
layout(binding=0) readonly buffer source_blob { float source_data[]; };
layout(binding=1) writeonly buffer target_blob { float target_data[]; };
layout(push_constant) uniform parameter { int w;int h;int source_step;int target_step; } p;
void main() {
    int x=int(gl_GlobalInvocationID.x),y=int(gl_GlobalInvocationID.y),c=int(gl_GlobalInvocationID.z);
    if(x>=p.w||y>=p.h||c>=3)return;
    precise float scaled=source_data[c*p.source_step+y*p.w+x]*255.0;
    precise float normalized=scaled*uintBitsToFloat(0x3b808081u);
    target_data[c*p.target_step+y*p.w+x]=normalized;
})glsl";
        std::vector<uint32_t> spirv;
        if(ncnn::compile_spirv_module(shader,sizeof(shader)-1,fp32,spirv))throw std::runtime_error("SPAN boundary shader compilation failed");
        pipeline_=std::make_unique<ncnn::Pipeline>(device);
        pipeline_->set_optimal_local_size_xyz(8,8,1);
        if(pipeline_->create(spirv.data(),spirv.size()*sizeof(uint32_t),{}))
            throw std::runtime_error("SPAN boundary pipeline creation failed");
    }

    ncnn::VkMat record(const ncnn::VkMat &source,ncnn::VkCompute &command,
                       const ncnn::Option &next,std::vector<ncnn::VkMat> &owners) const {
        if(source.dims!=3||source.c*source.elempack!=3)
            throw std::runtime_error("SPAN resident output must be three spatial channels");
        ncnn::VkMat fp32,normalized,result;
        // cast_type_to=1 is precisely NCNN's F32 unpacked host representation.
        device_->convert_packing(source,fp32,1,1,command,next);
        if(fp32.empty()||fp32.elembits()!=32||fp32.elempack!=1)
            throw std::runtime_error("SPAN resident F32 conversion failed");
        normalized.create(fp32.w,fp32.h,3,4u,1,next.blob_vkallocator);
        if(normalized.empty())throw std::runtime_error("SPAN resident boundary allocation failed");
        std::vector<ncnn::vk_constant_type> constants(4);
        constants[0].i=fp32.w;constants[1].i=fp32.h;
        constants[2].i=(int)fp32.cstep;constants[3].i=(int)normalized.cstep;
        command.record_pipeline(pipeline_.get(),{fp32,normalized},constants,normalized);
        // Match record_upload: RGB has pack1 and uses FP16 iff requested. This
        // uses NCNN's conversion, not a replacement model or a fused multiply.
        const int cast=(next.use_fp16_storage||next.use_fp16_packed)?2:1;
        device_->convert_packing(normalized,result,1,cast,command,next);
        if(result.empty())throw std::runtime_error("SPAN resident input storage conversion failed");
        owners.push_back(fp32);owners.push_back(normalized);owners.push_back(result);
        return result;
    }
private:
    const ncnn::VulkanDevice *device_;
    std::unique_ptr<ncnn::Pipeline> pipeline_;
};
