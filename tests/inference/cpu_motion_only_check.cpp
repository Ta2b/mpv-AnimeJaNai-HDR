// Raw flow/mask parity, context geometry replacement and forbidden RGB consumer.
#include "engine.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <iostream>

int main(int argc,char **argv) {
    if(argc!=3)return 2;
    try {
        const char *activation_flag=std::getenv("AJI_ORT_CPU_ACTIVATIONS");
        const bool activation_off=activation_flag && *activation_flag=='0';
        std::vector<std::pair<int,int>> shapes{{128,72}};
        if(!activation_off)shapes.emplace_back(160,80);
        for(const auto dimensions : shapes) {
            const int w=dimensions.first,h=dimensions.second;
            const ptrdiff_t stride=3*w+17;
            std::vector<uint8_t> a(stride*h,0xa5),b(stride*h,0xa5);
            for(int y=0;y<h;++y)for(int x=0;x<w;++x)for(int c=0;c<3;++c) {
                a[y*stride+3*x+c]=(uint8_t)(x*3+y*7+c*13);
                b[y*stride+3*x+c]=(uint8_t)(x*3+y*7+c*13+37);
            }
            aji::InterpolatorRequest request;
            request.provider="cpu";request.device="cpu";request.models_dir=argv[1];request.model=argv[2];
            request.width=w;request.height=h;request.motion_only=true;
            setenv("AJI_ORT_CPU_MOTION_ONLY","0",1);
            auto reference=aji::make_ort_interpolator(request);
            setenv("AJI_ORT_CPU_MOTION_ONLY","1",1);
            auto candidate=aji::make_ort_interpolator(request);
            if(!reference->has_motion() || !candidate->has_motion())return 1;
            std::vector<float> af,am,bf,bm;
            reference->motion(a.data(),stride,b.data(),stride,.5,af,am);
            candidate->motion(a.data(),stride,b.data(),stride,.5,bf,bm);
            if(af.size()!=4*(size_t)w*h || am.size()!=(size_t)w*h || af.size()!=bf.size() || am.size()!=bm.size()
                || std::memcmp(af.data(),bf.data(),af.size()*sizeof(float))
                || std::memcmp(am.data(),bm.data(),am.size()*sizeof(float))) {
                std::cerr<<"Raw motion differs at "<<w<<'x'<<h<<'\n';return 1;
            }
            std::vector<uint8_t> image(stride*h,0xa5);bool refused=false;
            try {candidate->run(a.data(),stride,b.data(),stride,.5,image.data(),stride);}
            catch(const std::exception &e) {refused=std::string(e.what()).find("flow/mask")!=std::string::npos;}
            if(!refused || !std::all_of(image.begin(),image.end(),[](uint8_t v){return v==0xa5;}))return 1;
            std::cout<<w<<'x'<<h<<": raw flow/mask bits identical; RGB request refused before writing\n";
        }
    }catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
