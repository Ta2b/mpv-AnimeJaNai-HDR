// HIP kernels for the existing RGB bridge. Keep the CPU reference's geometry,
// padding, normalization, clipping and rounding. Do not enable fast-math.
#include "hip_kernels.h"
#include <hip/hip_runtime.h>
#include <cmath>

namespace aji::amd {
namespace {
template<class T> __device__ float read(const T *p, size_t i) { return (float)p[i]; }
template<class T> __device__ void write(T *p, size_t i, float v) { p[i] = (T)v; }
__device__ float clip(float v, float a, float b) { return fminf(fmaxf(v, a), b); }
template<class T> __global__ void pack(const uint8_t *rgb, T *out, int w, int h,
                                     int pw, int ph, int left, int top) {
    const size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= (size_t)w * h) return;
    const size_t at = (i / w + top) * pw + i % w + left, plane = (size_t)pw * ph;
    for (int c = 0; c < 3; ++c) write(out, c * plane + at, rgb[3*i+c] * (1.0f/255.0f));
}
template<class T> __global__ void grid(T *out, int pw, int ph) {
    const size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x, n = (size_t)pw*ph;
    if (i >= n) return;
    write(out, 7*n+i, 2.0f * (i%pw) / (pw-1) - 1.0f);
    write(out, 8*n+i, 2.0f * (i/pw) / (ph-1) - 1.0f);
    write(out, 9*n+i, 2.0f / (pw-1)); write(out, 10*n+i, 2.0f / (ph-1));
}
template<class T> __global__ void fill_time(T *out, size_t n, float t) {
    const size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) write(out, 6*n+i, t);
}
template<class T> __global__ void unpack(const T *in, uint8_t *rgb, int pw, int ph,
                                       int x, int y, int w, int h) {
    const size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= (size_t)w*h) return;
    const size_t at = (i/w+y)*pw+i%w+x, plane = (size_t)pw*ph;
    for (int c=0;c<3;++c) rgb[3*i+c] = (uint8_t)clip(read(in,c*plane+at)*255.0f+0.5f,0,255);
}
template<class T> __global__ void crop(const T *in, float *out, int planes, int pw,
                                     int ph, int left, int top, int w, int h) {
    const size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x, n = (size_t)w*h;
    if (i >= n*planes) return;
    const size_t k=i/n, at=i%n;
    out[i]=read(in,k*(size_t)pw*ph+(at/w+top)*pw+at%w+left);
}
__global__ void maximum(const float *flow,size_t count,unsigned int *out) {
    const size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x;
    unsigned int bits=0;
    const float v=i<count?fabsf(flow[i]):0;
    // Match std::max(largest, fabs(v)): NaNs never replace the current maximum.
    if(v==v) { union { float value;unsigned int bits; } cast;cast.value=v;bits=cast.bits; }
    __shared__ unsigned int partial[256];partial[threadIdx.x]=bits;__syncthreads();
    for(unsigned int offset=128;offset;offset/=2) {
        if(threadIdx.x<offset) partial[threadIdx.x]=max(partial[threadIdx.x],partial[threadIdx.x+offset]);
        __syncthreads();
    }
    if(threadIdx.x==0) atomicMax(out,partial[0]);
}
__device__ float plane_sample(const float *p,int w,int h,float x,float y) {
    x=clip(x,0,w-1);y=clip(y,0,h-1);
    const int x0=(int)x,y0=(int)y,x1=min(x0+1,w-1),y1=min(y0+1,h-1);
    const float fx=x-x0,fy=y-y0;
    return (p[(size_t)y0*w+x0]*(1-fx)+p[(size_t)y0*w+x1]*fx)*(1-fy)
         + (p[(size_t)y1*w+x0]*(1-fx)+p[(size_t)y1*w+x1]*fx)*fy;
}
__device__ float rgb_sample(const uint8_t *p,int w,int h,float x,float y,int c) {
    x=clip(x,0,w-1);y=clip(y,0,h-1);
    const int x0=(int)x,y0=(int)y,x1=min(x0+1,w-1),y1=min(y0+1,h-1);
    const float fx=x-x0,fy=y-y0;
    return (p[((size_t)y0*w+x0)*3+c]*(1-fx)+p[((size_t)y0*w+x1)*3+c]*fx)*(1-fy)
         + (p[((size_t)y1*w+x0)*3+c]*(1-fx)+p[((size_t)y1*w+x1)*3+c]*fx)*fy;
}
template<class T> __device__ float tensor_sample(const T *p,int w,int h,float x,float y,int c) {
    x=clip(x,0,w-1);y=clip(y,0,h-1);
    const int x0=(int)x,y0=(int)y,x1=min(x0+1,w-1),y1=min(y0+1,h-1);
    const size_t n=(size_t)c*w*h;const float fx=x-x0,fy=y-y0;
    return (read(p,n+(size_t)y0*w+x0)*(1-fx)+read(p,n+(size_t)y0*w+x1)*fx)*(1-fy)
         + (read(p,n+(size_t)y1*w+x0)*(1-fx)+read(p,n+(size_t)y1*w+x1)*fx)*fy;
}
template<class T> __global__ void warp_float(const T *a,const T *b,T *out,int w,int h,
                     const float *f,const float *mask,int fw,int fh,float t,
                     bool derived,float time_term) {
    const size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x,n=(size_t)fw*fh;
    if(i >= (size_t)w*h) return;
    const int x=i%w,y=i/w;const float sx=(float)w/fw,sy=(float)h/fh;
    float u=(x+0.5f)/sx-0.5f,v=(y+0.5f)/sy-0.5f;
    float dx0=plane_sample(f,fw,fh,u,v),dy0=plane_sample(f+n,fw,fh,u,v);
    float dx1=plane_sample(f+2*n,fw,fh,u,v),dy1=plane_sample(f+3*n,fw,fh,u,v);
    float m;
    if(derived && t != 0.5f) {
        u-=((1-t)*dx0+t*dx1);v-=((1-t)*dy0+t*dy1);
        const float tx=plane_sample(f+2*n,fw,fh,u,v)-plane_sample(f,fw,fh,u,v);
        const float ty=plane_sample(f+3*n,fw,fh,u,v)-plane_sample(f+n,fw,fh,u,v);
        dx0=-t*tx;dy0=-t*ty;dx1=(1-t)*tx;dy1=(1-t)*ty;
        const float mm=clip(plane_sample(mask,fw,fh,u,v),1e-4f,1-1e-4f);
        m=1.0f/(1.0f+expf(-(0.285f*logf(mm/(1-mm))+time_term)));
    } else m=plane_sample(mask,fw,fh,u,v);
    for(int c=0;c<3;++c) write(out,(size_t)c*w*h+i,
        tensor_sample(a,w,h,x+sx*dx0,y+sy*dy0,c)*m
        +tensor_sample(b,w,h,x+sx*dx1,y+sy*dy1,c)*(1-m));
}
__global__ void warp(const uint8_t *a,const uint8_t *b,uint8_t *out,int w,int h,
                     const float *f,const float *mask,int fw,int fh,float t,
                     bool derived,float time_term) {
    const size_t i=(size_t)blockIdx.x*blockDim.x+threadIdx.x,n=(size_t)fw*fh;
    if(i >= (size_t)w*h) return;
    const int x=i%w,y=i/w;const float sx=(float)w/fw,sy=(float)h/fh;
    float u=(x+0.5f)/sx-0.5f,v=(y+0.5f)/sy-0.5f;
    float dx0=plane_sample(f,fw,fh,u,v),dy0=plane_sample(f+n,fw,fh,u,v);
    float dx1=plane_sample(f+2*n,fw,fh,u,v),dy1=plane_sample(f+3*n,fw,fh,u,v);
    float m;
    if(derived && t != 0.5f) {
        u-=((1-t)*dx0+t*dx1);v-=((1-t)*dy0+t*dy1);
        const float tx=plane_sample(f+2*n,fw,fh,u,v)-plane_sample(f,fw,fh,u,v);
        const float ty=plane_sample(f+3*n,fw,fh,u,v)-plane_sample(f+n,fw,fh,u,v);
        dx0=-t*tx;dy0=-t*ty;dx1=(1-t)*tx;dy1=(1-t)*ty;
        const float mm=clip(plane_sample(mask,fw,fh,u,v),1e-4f,1-1e-4f);
        m=1.0f/(1.0f+expf(-(0.285f*logf(mm/(1-mm))+time_term)));
    } else m=plane_sample(mask,fw,fh,u,v);
    for(int c=0;c<3;++c) {
        const float value=rgb_sample(a,w,h,x+sx*dx0,y+sy*dy0,c)*m
                         +rgb_sample(b,w,h,x+sx*dx1,y+sy*dy1,c)*(1-m);
        out[3*i+c]=(uint8_t)clip(value+0.5f,0,255);
    }
}
unsigned blocks(size_t n) { return (unsigned)((n+255)/256); }
}
hipError_t pack_rgb(const uint8_t *in,void *out,bool half,int w,int h,int pw,int ph,int l,int top,hipStream_t s) {
    if(half) hipLaunchKernelGGL(pack<_Float16>,dim3(blocks((size_t)w*h)),dim3(256),0,s,in,(_Float16*)out,w,h,pw,ph,l,top);
    else hipLaunchKernelGGL(pack<float>,dim3(blocks((size_t)w*h)),dim3(256),0,s,in,(float*)out,w,h,pw,ph,l,top);
    return hipGetLastError();
}
hipError_t rife_grid(void *out,bool half,int pw,int ph,hipStream_t s) {
    if(half) hipLaunchKernelGGL(grid<_Float16>,dim3(blocks((size_t)pw*ph)),dim3(256),0,s,(_Float16*)out,pw,ph);
    else hipLaunchKernelGGL(grid<float>,dim3(blocks((size_t)pw*ph)),dim3(256),0,s,(float*)out,pw,ph);
    return hipGetLastError();
}
hipError_t timestep(void *out,bool half,int pw,int ph,float t,hipStream_t s) {
    if(half) hipLaunchKernelGGL(fill_time<_Float16>,dim3(blocks((size_t)pw*ph)),dim3(256),0,s,(_Float16*)out,(size_t)pw*ph,t);
    else hipLaunchKernelGGL(fill_time<float>,dim3(blocks((size_t)pw*ph)),dim3(256),0,s,(float*)out,(size_t)pw*ph,t);
    return hipGetLastError();
}
hipError_t unpack_rgb(const void *in,bool half,uint8_t *out,int pw,int ph,int x,int y,int w,int h,hipStream_t s) {
    if(half) hipLaunchKernelGGL(unpack<_Float16>,dim3(blocks((size_t)w*h)),dim3(256),0,s,(const _Float16*)in,out,pw,ph,x,y,w,h);
    else hipLaunchKernelGGL(unpack<float>,dim3(blocks((size_t)w*h)),dim3(256),0,s,(const float*)in,out,pw,ph,x,y,w,h);
    return hipGetLastError();
}
hipError_t crop_planes(const void *in,bool half,float *out,int planes,int pw,int ph,int l,int top,int w,int h,hipStream_t s) {
    if(half) hipLaunchKernelGGL(crop<_Float16>,dim3(blocks((size_t)w*h*planes)),dim3(256),0,s,(const _Float16*)in,out,planes,pw,ph,l,top,w,h);
    else hipLaunchKernelGGL(crop<float>,dim3(blocks((size_t)w*h*planes)),dim3(256),0,s,(const float*)in,out,planes,pw,ph,l,top,w,h);
    return hipGetLastError();
}
hipError_t flow_max(const float *in,size_t count,unsigned int *out,hipStream_t s) {
    hipLaunchKernelGGL(maximum,dim3(blocks(count)),dim3(256),0,s,in,count,out);
    return hipGetLastError();
}
hipError_t warp_rgb(const uint8_t *a,const uint8_t *b,uint8_t *out,int w,int h,const float *f,const float *m,int fw,int fh,float t,bool derived,hipStream_t s) {
    const float term=derived && t!=0.5f ? 2.591f*std::log((1-t)/t)+0.170f : 0;
    hipLaunchKernelGGL(warp,dim3(blocks((size_t)w*h)),dim3(256),0,s,a,b,out,w,h,f,m,fw,fh,t,derived,term);
    return hipGetLastError();
}
hipError_t warp_tensor(const void *a,const void *b,void *out,bool half,int w,int h,
    const float *f,const float *m,int fw,int fh,float t,bool derived,hipStream_t s) {
    const float term=derived && t!=0.5f ? 2.591f*std::log((1-t)/t)+0.170f : 0;
    if(half) hipLaunchKernelGGL(warp_float<_Float16>,dim3(blocks((size_t)w*h)),dim3(256),0,s,
        (const _Float16*)a,(const _Float16*)b,(_Float16*)out,w,h,f,m,fw,fh,t,derived,term);
    else hipLaunchKernelGGL(warp_float<float>,dim3(blocks((size_t)w*h)),dim3(256),0,s,
        (const float*)a,(const float*)b,(float*)out,w,h,f,m,fw,fh,t,derived,term);
    return hipGetLastError();
}
}
