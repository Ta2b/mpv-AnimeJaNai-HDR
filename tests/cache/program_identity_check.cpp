#include "../../native/common/program_identity.h"
#include <cassert>
#include <iostream>
#include <functional>
using namespace aji::identity;
int main()
{
    Program base;
    base.format = ProgramFormat::TensorRT;
    base.source_scheme = "onnx-source-v2"; base.source_digest = std::string(64, 'a');
    base.converter = "onnx-to-tensorrt"; base.converter_version = 1;
    base.options = "--stronglyTyped";
    base.io_policy = IoPolicy::Specialized;
    base.bindings = {{"input", "float16", {1,3,72,128}}};
    base.compiler = "TRT11.3.0.99"; base.runtime = "CUDA13.4/TRT11.3"; base.device = "sm89/uuid/driver615";
    const auto original = program_key(base);
    unsigned invalidations = 0, refusals = 0;
    auto changed = [&](const std::function<void(Program &)> &edit) {
        auto p = base; edit(p); assert(program_key(p) != original); ++invalidations;
    };
    changed([](Program &p){p.source_digest[0]='b';}); // graph or external weight content
    changed([](Program &p){p.source_scheme="source-v3";});
    changed([](Program &p){p.converter="different-transform";});
    changed([](Program &p){++p.converter_version;});
    changed([](Program &p){p.options+=" --fp32";});
    changed([](Program &p){p.build_environment="env CUDA_MODULE_LOADING=EAGER";});
    changed([](Program &p){p.bindings[0].dimensions[2]=74;});
    changed([](Program &p){p.bindings[0].type="float32";});
    changed([](Program &p){p.bindings[0].name="other-input";});
    changed([](Program &p){p.compiler+="-new";});
    changed([](Program &p){p.runtime+="-new";});
    changed([](Program &p){p.device+="-new";});
    changed([](Program &p){p.io_policy=IoPolicy::SourceDefined;p.bindings.clear();});
    for (auto format : {ProgramFormat::CoreML,ProgramFormat::OrtProvider,ProgramFormat::MIGraphX})
        changed([&](Program &p){p.format=format;});
    // Named bindings are a set; vector iteration order cannot affect identity.
    auto p=base; p.bindings.push_back({"second", "float32", {1,1,-1,-1}});
    const auto two=program_key(p); std::reverse(p.bindings.begin(),p.bindings.end());
    assert(two==program_key(p));
    // Length framing prevents concatenation/field-boundary collisions.
    p=base; p.converter="a"; p.options="bc"; const auto framed=program_key(p);
    p.converter="ab"; p.options="c"; assert(program_key(p)!=framed);
    auto refused = [&](Program p) { bool threw=false;try{program_key(p);}catch(const std::invalid_argument &){threw=true;}assert(threw);++refusals; };
    p=base;p.source_digest="unknown";refused(p);
    p=base;p.source_scheme.clear();refused(p);
    p=base;p.converter_version=0;refused(p);
    p=base;p.compiler.clear();refused(p);
    p=base;p.runtime.clear();refused(p);
    p=base;p.device.clear();refused(p);
    p=base;p.bindings[0].dimensions[0]=0;refused(p);
    p=base;p.bindings.push_back(p.bindings[0]);refused(p);
    p=base;p.io_policy=IoPolicy::SourceDefined;refused(p);
    p=base;p.format=static_cast<ProgramFormat>(99);refused(p);
    p=base;p.format=ProgramFormat::OnnxExport;refused(p);
    p.compiler.clear();p.runtime.clear();p.device.clear();
    const auto portable=program_key(p); assert(portable!=original);
    p.build_environment="export-option";assert(program_key(p)!=portable);
    std::cout << "{\"passed\":true,\"field_invalidations\":" << invalidations
              << ",\"invalid_contracts_refused\":" << refusals
              << ",\"named_binding_order_stable\":true,\"framing_collision_refused\":true,\"native_other_providers\":false}\n";
}
