#include "aji_conf.h"
#include <iostream>
#include <iomanip>
int main(int argc, char **argv) {
    AjiConf c; std::string why;
    if (argc != 2 || !aji_conf_load(argv[1], &c, &why)) { std::cerr << why; return 2; }
    const auto &ch = c.slots.at(1).chains.at(0);
    std::cout << "{\"temporal\":\"" << (c.rife_warp ? "fast" : "quality")
        << "\",\"drawings_configured\":" << c.rife_drawings
        << ",\"drawings_effective_policy\":" << (c.rife_warp && c.rife_drawings)
        << ",\"rife\":" << ch.rife << ",\"model\":" << std::quoted(ch.models.at(0).name)
        << ",\"rife_model\":" << ch.rife_model << ",\"ensemble\":" << ch.rife_ensemble
        << ",\"factor_num\":" << ch.rife_factor_num << ",\"factor_den\":" << ch.rife_factor_den
        << ",\"rife_before_upscale\":" << ch.rife_before_upscale << "}\n";
}
