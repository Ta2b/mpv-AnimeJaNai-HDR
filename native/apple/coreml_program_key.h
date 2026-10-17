#pragma once
#include "../common/program_identity.h"

namespace aji::coreml {
// Observed compile compatibility, supplied by the Apple consumer. A .mlmodelc
// is compiled from a package before MLModelConfiguration selects compute units,
// GPU accumulation and optimization hints. Those load-time choices remain in
// the placement key, not this reusable package compilation key.
struct CompileEnvironment {
    std::string framework_version, os_build, host_architecture;
};
inline std::string program_key(const std::string &template_tag, int width, int height,
                               const CompileEnvironment &environment)
{
    if (template_tag.size()!=67 || template_tag.compare(0,3,"v2-")!=0)
        throw std::invalid_argument("Core ML template content identity v2 required");
    if (environment.framework_version.empty() || environment.os_build.empty() || environment.host_architecture.empty())
        throw std::invalid_argument("Core ML compile compatibility metadata missing");
    identity::Program program;
    program.format=identity::ProgramFormat::CoreML;
    program.source_scheme="coreml-native-template-v2";program.source_digest=template_tag.substr(3);
    program.converter="native-coreml-size-patch";program.converter_version=1;
    program.options="AJP1;compileModelAtURL:no-configuration;image-input-output-rgb8";
    program.io_policy=identity::IoPolicy::Specialized;
    program.bindings={{"input","image-rgb8",{height,width,3}},
                      {"output","image-rgb8",{int64_t(height)*2,int64_t(width)*2,3}}};
    program.compiler="CoreML/"+environment.framework_version;
    program.runtime=environment.os_build;
    program.device="host-compiler/"+environment.host_architecture;
    return identity::program_key(std::move(program));
}
} // namespace aji::coreml
