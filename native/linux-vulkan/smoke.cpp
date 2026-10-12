#include "aji_vulkan.h"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc,char **argv) {
    if(argc!=8){std::cerr<<"usage: test CONF MODELS RIFE DEVICE SLOT SIZE OUTPUT\n";return 2;}
    auto c=aji_vk_create(argv[1],argv[2],argv[3],argv[4],"",std::atoi(argv[5]));
    if(!c){std::cerr<<aji_vk_error(nullptr)<<"\n";return 1;}
    int size=std::atoi(argv[6]);aji_vk_plan p;
    if(aji_vk_configure(c,size,size,24,&p)){std::cerr<<aji_vk_error(c)<<"\n";aji_vk_destroy(c);return 1;}
    std::vector<unsigned char> a(size*size*3),b(a.size()),out(p.width*p.height*3);
    for(int y=0;y<size;++y)for(int x=0;x<size;++x)for(int k=0;k<3;++k){
        a[(y*size+x)*3+k]=(x*3+y*2+k*30)%256;b[(y*size+x)*3+k]=(x*3+y*2+k*30+12)%256;
    }
    if(aji_vk_process(c,a.data(),size*3,b.data(),size*3,p.numerator>p.denominator?.5:1,out.data(),p.width*3)){
        std::cerr<<aji_vk_error(c)<<"\n";aji_vk_destroy(c);return 1;
    }
    auto bounds=std::minmax_element(out.begin(),out.end());
    if(*bounds.first==*bounds.second){std::cerr<<"Inference returned a constant image\n";aji_vk_destroy(c);return 1;}
    std::ofstream f(argv[7],std::ios::binary);f.write((char*)out.data(),out.size());
    std::cout<<"PASS Vulkan output="<<p.width<<"x"<<p.height<<" factor="<<p.numerator<<"/"<<p.denominator<<"\n";
    aji_vk_destroy(c);return 0;
}
