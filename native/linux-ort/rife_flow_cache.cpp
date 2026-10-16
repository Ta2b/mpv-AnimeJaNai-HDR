#include "rife_flow_cache.h"
#include "onnx_flow.h"
#include "../common/content_identity.h"
#include "../common/cache_key_lock.h"
#include "../common/cache_stage_owner.h"
#include <iostream>
#include <random>

namespace aji {
namespace {
namespace fs = std::filesystem;
// Bump when the transformation's semantics change. Identity is independent of
// device/shape: this is an ONNX export, not a device-compiled program.
constexpr const char *version = "rife-flow-outputs-v2";
constexpr const char *graph_name = "rife.flow.onnx";

std::string source_key(const std::vector<char> &graph, const std::vector<identity::File> &weights)
{
    identity::Sha256 hash;
    hash.text(version); hash.integer(graph.size()); hash.update(graph.data(),graph.size());
    hash.text(identity::files("onnx-external-weights-v1",weights));
    return hash.hex();
}
fs::path temporary(const fs::path &parent, const std::string &prefix)
{
    std::random_device random;
    for (unsigned i = 0; i < 16; ++i) {
        auto path = parent / (prefix + std::to_string(random()) + "-" + std::to_string(random()));
        if (fs::create_directory(path)) return path;
    }
    throw std::runtime_error("Cannot reserve RIFE cache staging directory");
}
struct Stage {
    fs::path path;
    ~Stage() { cache::cleanup_stage(path); }
};
std::vector<identity::File> cache_files(const fs::path &directory, const std::vector<std::string> &locations)
{
    std::vector<identity::File> result{{"graph",directory / graph_name}};
    for (const auto &location : locations) result.emplace_back("external/"+location,directory / fs::u8path(location));
    return result;
}
bool valid(const fs::path &directory, const std::vector<std::string> &locations)
{
    try {
        std::ifstream stamp(directory / "ready.sha256"); std::string expected, extra;
        if (!std::getline(stamp,expected) || expected.size() != 64 || std::getline(stamp,extra)) return false;
        return expected == identity::files(version,cache_files(directory,locations));
    } catch (const std::exception &) { return false; }
}
}

fs::path cached_rife_flow(const fs::path &source, const fs::path &cache)
{
    std::ifstream in(source,std::ios::binary);
    if (!in) throw std::runtime_error("Cannot read RIFE source: "+source.string());
    std::vector<char> graph((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    if (in.bad() || graph.empty()) throw std::runtime_error("Incomplete RIFE source: "+source.string());
    std::string why; std::vector<std::string> locations;
    if (!aji_onnx_external_locations(graph,&locations,&why)) throw std::runtime_error(why);
    std::vector<identity::File> weights;
    for (const auto &location : locations) {
        const fs::path relative = fs::u8path(location);
        if (relative.empty() || relative.is_absolute() || relative.has_root_name()
            || location.find('\\') != std::string::npos || location.find(':') != std::string::npos)
            throw std::runtime_error("RIFE external weight path must be relative: "+location);
        for (const auto &part : relative) if (part == "..") throw std::runtime_error("RIFE external weight escapes its folder: "+location);
        if (relative.lexically_normal() == graph_name || relative.lexically_normal() == "ready.sha256")
            throw std::runtime_error("RIFE external weight conflicts with cache metadata: "+location);
        weights.emplace_back("external/"+location,source.parent_path()/relative);
    }
    const std::string key = source_key(graph,weights);
    const fs::path parent = cache / "rife-flow-v2", destination = parent / key;
    fs::create_directories(parent);
    if (valid(destination,locations) && !cache::has_owned_stages(parent,".part-","flow:"+key))
        return destination / graph_name;
    cache::KeyLock lock(parent / (key + ".key-lock"));
    cache::recover_owned_stages(parent, ".part-", "flow:" + key);
    if (valid(destination,locations)) return destination / graph_name;

    Stage stage{temporary(parent,".part-")};
    cache::mark_stage(stage.path, "flow:" + key);
    const auto data=stage.path/"data";fs::create_directory(data);
    std::vector<char> flow;
    if (!aji_onnx_add_flow_outputs(graph,&flow,&why)) throw std::runtime_error("No RIFE motion output: "+why);
    for (const auto &location : locations) {
        const fs::path target = data / fs::u8path(location);
        fs::create_directories(target.parent_path());
        fs::copy_file(source.parent_path()/fs::u8path(location),target);
    }
    std::vector<identity::File> staged_weights;
    for (const auto &location : locations) staged_weights.emplace_back("external/"+location,data/fs::u8path(location));
    if (source_key(graph,staged_weights) != key) throw std::runtime_error("RIFE weights changed during export");
    {
        std::ofstream out(data/graph_name,std::ios::binary);
        out.write(flow.data(),(std::streamsize)flow.size()); out.close();
        if (!out) throw cache::io_error("write RIFE flow graph",data/graph_name);
    }
    const std::string digest = identity::files(version,cache_files(data,locations));
    {
        std::ofstream stamp(data/"ready.sha256"); stamp << digest << '\n'; stamp.close();
        if (!stamp) throw cache::io_error("write RIFE flow cache identity",data/"ready.sha256");
    }
    if (!valid(data,locations)) throw std::runtime_error("Incomplete RIFE staged export");

    // Another process may have completed the same key while we transformed it.
    if (valid(destination,locations)) return destination / graph_name;
    if (fs::exists(destination)) {
        const fs::path quarantine = temporary(parent,".invalid-");
        std::error_code error; fs::rename(destination,quarantine/"preserved",error);
        if (error && !valid(destination,locations)) throw std::runtime_error("Cannot preserve damaged RIFE cache: "+error.message());
    }
    std::error_code error; fs::rename(data,destination,error);
    if (error && !valid(destination,locations)) throw std::runtime_error("Cannot publish RIFE flow cache: "+error.message());
    std::cerr << "[aji] RIFE flow export " << version << " content " << key << ": " << destination.string() << '\n';
    return destination / graph_name;
}
}
