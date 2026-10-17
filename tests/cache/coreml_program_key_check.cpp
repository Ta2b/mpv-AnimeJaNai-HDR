#include "../../native/apple/coreml_program_key.h"
#include <cassert>
#include <iostream>

int main()
{
    using namespace aji::coreml;
    const std::string content="v2-"+std::string(64,'a');
    CompileEnvironment environment{"CoreML-build-a","Version 15.7.9 (Build 24G830)","arm64"};
    const auto key=program_key(content,1280,720,environment);
    assert(key==program_key(content,1280,720,environment));
    assert(key!=program_key("v2-"+std::string(64,'b'),1280,720,environment));
    assert(key!=program_key(content,1282,720,environment));
    assert(key!=program_key(content,1280,722,environment));
    auto changed=environment;changed.framework_version+="2";
    assert(key!=program_key(content,1280,720,changed));
    changed=environment;changed.os_build+="1";
    assert(key!=program_key(content,1280,720,changed));
    changed=environment;changed.host_architecture="x86_64";
    assert(key!=program_key(content,1280,720,changed));
    auto rejected=[](auto operation){try{operation();return false;}catch(const std::invalid_argument&){return true;}};
    assert(rejected([&]{program_key("legacy-tag",1280,720,environment);}));
    assert(rejected([&]{program_key("v2-"+std::string(64,'z'),1280,720,environment);}));
    assert(rejected([&]{program_key(content,0,720,environment);}));
    changed=environment;changed.framework_version.clear();
    assert(rejected([&]{program_key(content,1280,720,changed);}));
    std::cout<<"PASS: content, shapes, framework, OS build and host architecture participate; incomplete identities rejected\n";
}
