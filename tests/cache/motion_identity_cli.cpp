#include "model_identity.h"
#include "onnx_flow.h"
#include "onnx_shape.h"
#include <fstream>
#include <iostream>
int main(int argc,char **argv)
{
    try {
        if(argc!=4)return 2;
        const auto path=std::filesystem::u8path(argv[2]);
        if(std::string(argv[1])=="transform") {
            std::ifstream in(path,std::ios::binary);
            std::vector<char> blob((std::istreambuf_iterator<char>(in)),{}),made;
            std::string why;if(!aji_onnx_motion_outputs(blob,&made,&why))throw std::runtime_error(why);
            std::ofstream out(std::filesystem::u8path(argv[3]),std::ios::binary);
            out.write(made.data(),made.size());if(!out)throw std::runtime_error("write fixture failed");
        } else {
            auto cache=std::filesystem::u8path(argv[3]);
            auto source=aji::cache::freeze_model(path,cache/"sources");
            auto motion=aji::cache::freeze_motion_model(source,cache/"motion-v3");
            std::cout<<motion.content<<'\n'<<motion.directory<<'\n'<<motion.scheme<<'\n';
        }
    }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
