#include "../../native/linux-ort/rife_flow_cache.h"
#include "../../native/linux-ort/onnx_flow.h"
#include <fstream>
#include <iostream>

int main(int argc, char **argv)
{
    try {
        if (argc != 3) return 2;
        if (std::string(argv[1]) == "--locations") {
            std::ifstream file(argv[2],std::ios::binary);
            std::vector<char> graph((std::istreambuf_iterator<char>(file)),std::istreambuf_iterator<char>());
            std::vector<std::string> locations;std::string why;
            if (!aji_onnx_external_locations(graph,&locations,&why)) throw std::runtime_error(why);
            for (auto &location : locations) std::cout << location << '\n';
        } else std::cout << aji::cached_rife_flow(argv[1],argv[2]).string() << '\n';
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
