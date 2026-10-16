#include "onnx_flow.h"
#include <fstream>
#include <iterator>
extern "C" int aji_test_cpu_activation_graph(const char *source,const char *destination,size_t *count) {
    std::ifstream in(source,std::ios::binary);
    std::vector<char> original((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>()),changed;
    if(!aji_onnx_cpu_activations(original,&changed,count))return 0;
    std::ofstream out(destination,std::ios::binary);out.write(changed.data(),changed.size());return out.good()?1:-1;
}
