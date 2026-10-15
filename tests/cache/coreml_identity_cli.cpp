#include "../../native/common/content_identity.h"
#include "../../native/linux-ort/mlpatch.h"
#include <iostream>

int main(int argc, char **argv)
{
    try {
        if (argc == 3 && std::string(argv[1]) == "--sha") {
            std::ifstream in(argv[2], std::ios::binary);
            if (!in) return 2;
            aji::identity::Sha256 hash; char buffer[17];
            while (in) { in.read(buffer, sizeof buffer); hash.update(buffer, (size_t)in.gcount()); }
            std::cout << hash.hex() << '\n';
        } else if (argc == 7 && std::string(argv[1]) == "--write") {
            aji::write_coreml_package(argv[2], argv[3], std::stoi(argv[5]), std::stoi(argv[6]), argv[4]);
        } else if (argc == 3) std::cout << aji::coreml_template_tag(argv[1], argv[2]) << '\n';
        else return 2;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
