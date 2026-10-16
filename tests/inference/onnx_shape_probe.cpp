// Test-only interface to the production metadata transform; no model execution.
#include "onnx_flow.h"
#include <fstream>
#include <iterator>
#include <cstdio>

extern "C" int aji_test_fixed_shape(const char *source, const char *destination,
    int channels, int height, int width, char *reason, size_t size)
{
    std::ifstream in(source,std::ios::binary);
    std::vector<char> original((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>()), fixed;
    std::string why;
    const auto result = aji_onnx_fixed_rank4_input(original,{1,channels,height,width},&fixed,&why);
    std::snprintf(reason,size,"%s",why.c_str());
    if (result == AjiFixedShape::Specialized) {
        std::ofstream out(destination,std::ios::binary);
        out.write(fixed.data(),(std::streamsize)fixed.size());
        if (!out.good()) return -1;
    }
    return (int)result;
}
