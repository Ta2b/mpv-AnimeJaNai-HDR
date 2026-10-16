#pragma once
#include "surface.h"
#include <array>
#include <limits>
#include <stdexcept>

namespace aji::surface {
inline void check(bool ok,const char *why) { if(!ok)throw std::invalid_argument(why); }
struct Unsupported:std::invalid_argument { using std::invalid_argument::invalid_argument; };
inline void supported(bool ok,const char *why) { if(!ok)throw Unsupported(why); }
struct HostView {
    uint8_t *pixels=nullptr;
    ptrdiff_t stride=0;
    aji_surface_rect_v1 crop{};
    uintptr_t begin=0,end=0;
};
using Signature=std::array<uint64_t,25>;
inline Signature signature(const aji_surface_v1 &s,const HostView &v)
{
    return {s.resource_kind,s.format,s.device_kind,s.device_index,(uintptr_t)s.device_context,
        (uint32_t)s.width,(uint32_t)s.height,(uint32_t)v.crop.x,(uint32_t)v.crop.y,
        (uint32_t)v.crop.width,(uint32_t)v.crop.height,s.planes[0].offset,(uint64_t)s.planes[0].row_stride,
        s.rotation,s.vertical_flip,s.color.matrix,s.color.primaries,s.color.transfer,s.color.range,
        s.color.siting,s.color.component_bits,s.color.quantization,s.color.dither,s.generation,0};
}
inline bool same_color(const aji_surface_v1 &a,const aji_surface_v1 &b)
{
    const auto &x=a.color,&y=b.color;
    return x.matrix==y.matrix && x.primaries==y.primaries && x.transfer==y.transfer && x.range==y.range
        && x.siting==y.siting && x.component_bits==y.component_bits
        && a.rotation==b.rotation && a.vertical_flip==b.vertical_flip;
}
inline HostView host(const aji_surface_v1 *s,int expected_w,int expected_h,bool output)
{
    check(s && s->struct_size>=sizeof(*s) && s->version==1,"Invalid surface version/size");
    supported(s->resource_kind==AJI_RESOURCE_HOST && s->device_kind==AJI_RESOURCE_HOST && !s->device_index
        && !s->device_context && !s->resource && !s->subresource && !s->device_luid,
        "CPU surface requires a host resource/device");
    for(auto b:s->device_uuid)supported(!b,"CPU surface has an incompatible device UUID");
    supported(s->format==AJI_SURFACE_RGB8 && s->plane_count==1,"CPU surface accepts one RGB8 plane");
    check(s->width>0 && s->height>0 && s->width<=16384 && s->height<=16384,"Invalid surface allocation geometry");
    check(!s->reserved && !s->reserved_time && s->rotation<360 && s->rotation%90==0 && s->vertical_flip<=1,
        "Unsupported surface orientation/reserved fields");
    const auto &color=s->color;
    supported(color.matrix==AJI_SURFACE_MATRIX_RGB && color.range==AJI_SURFACE_RANGE_FULL && color.component_bits==8,
        "CPU RGB8 surface requires explicit full-range RGB encoding");
    supported(color.transfer>=AJI_SURFACE_TRC_709 && color.transfer<=AJI_SURFACE_TRC_1886,
        "CPU RGB8 surface requires an explicit SDR transfer");
    supported(color.primaries<=AJI_SURFACE_PRIM_601 && color.siting<=AJI_SURFACE_SITING_TOPLEFT
        && color.quantization==AJI_SURFACE_QUANT_REFERENCE_RGB8 && color.dither<=AJI_SURFACE_DITHER_NONE,
        "Unsupported surface color/quantization policy");
    supported(!output || color.dither==AJI_SURFACE_DITHER_NONE,"CPU output cannot add dither");
    check(!(s->time_flags&~3u) && (!(s->time_flags&3u) || (s->timebase_num>0 && s->timebase_den>0))
        && (!(s->time_flags&AJI_SURFACE_HAS_DURATION) || s->duration>=0),"Invalid surface timing metadata");
    check(bool(s->retain)==bool(s->release),"Surface retain/release must be paired");
    auto crop=s->crop;
    if(!crop.x && !crop.y && !crop.width && !crop.height)crop={0,0,s->width,s->height};
    check(crop.x>=0 && crop.y>=0 && crop.width>0 && crop.height>0 && crop.x<=s->width-crop.width
        && crop.y<=s->height-crop.height && crop.width==expected_w && crop.height==expected_h,
        "Surface active crop does not match configured geometry");
    const auto &p=s->planes[0];
    check(p.data && p.row_stride>0 && (uint64_t)p.row_stride<=PTRDIFF_MAX,"Invalid host surface stride/data");
    const uint64_t stride=p.row_stride,row=(uint64_t)s->width*3,rows=s->height-1;
    check(stride>=row && p.offset<=p.bytes && row<=p.bytes-p.offset,"Host surface row exceeds its extent");
    check(!rows || stride<=(p.bytes-p.offset-row)/rows,"Host surface rows exceed its extent");
    const uint64_t full=p.offset+rows*stride+row;
    check(full<=PTRDIFF_MAX && (uintptr_t)p.data<=UINTPTR_MAX-full,"Host surface address/extent overflow");
    const uint64_t start=p.offset+(uint64_t)crop.y*stride+(uint64_t)crop.x*3;
    const uintptr_t begin=(uintptr_t)p.data+start,end=begin+(uint64_t)(crop.height-1)*stride+(uint64_t)crop.width*3;
    return {(uint8_t *)begin,(ptrdiff_t)stride,crop,begin,end};
}
inline bool overlaps(const HostView &a,const HostView &b) { return a.begin<b.end && b.begin<a.end; }
class Owners {
    std::array<const aji_surface_v1 *,3> acquired{};
    size_t count=0;
public:
    void add(const aji_surface_v1 *s) { if(s && s->retain) {s->retain(s->owner);acquired[count++]=s;} }
    ~Owners() { while(count) {const auto *s=acquired[--count];s->release(s->owner);} }
    Owners()=default;Owners(const Owners &)=delete;Owners &operator=(const Owners &)=delete;
};
}
