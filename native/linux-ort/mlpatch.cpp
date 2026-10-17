#include "mlpatch.h"
#include "engine.h"
#include "../common/content_identity.h"
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <sstream>
#include <vector>

namespace aji {
namespace {

struct Table {
    int template_h = 0, template_w = 0;
    std::string model_path;
    size_t model_size = 0;
    std::map<std::string, std::vector<size_t>> offsets;   // h, w, h2, w2, hh, ww
};

Table read_table(const std::filesystem::path &path)
{
    std::ifstream file(path);
    require(file.good(), "Core ML size table not found: " + path.string());
    Table t;
    std::string line;
    bool header = false;
    while (std::getline(file, line)) {
        std::istringstream in(line);
        std::string word;
        if (!(in >> word)) continue;
        if (word == "AJP") { int version = 0; in >> version; require(version == 1, "Unsupported Core ML size table: " + path.string()); header = true; }
        else if (word == "template") in >> t.template_h >> t.template_w;
        else if (word == "model") in >> t.model_path >> t.model_size;
        else {
            size_t count = 0;
            in >> count;
            auto &list = t.offsets[word];
            for (size_t i = 0; i < count; i++) { size_t offset = 0; in >> offset; list.push_back(offset); }
            require(!in.fail(), "Malformed Core ML size table: " + path.string());
        }
    }
    require(header && t.template_h > 0 && t.template_w > 0 && !t.model_path.empty() && t.model_size > 0
            && !t.offsets["h"].empty() && !t.offsets["w"].empty(), "Incomplete Core ML size table: " + path.string());
    // Tables are external inputs. They may select only a file inside the owned
    // package, never a host path or a sibling of the transaction staging.
    const std::filesystem::path relative(t.model_path);
    require(!relative.is_absolute() && !relative.has_root_name() && !relative.has_root_directory(),
            "Absolute Core ML model path in size table: " + path.string());
    for(const auto &part:relative)
        require(part != ".." && part != "." && !part.empty(), "Unsafe Core ML model path in size table: " + path.string());
    return t;
}

std::vector<uint8_t> read_all(const std::filesystem::path &path)
{
    std::ifstream file(path, std::ios::binary);
    require(file.good(), "File not found: " + path.string());
    return std::vector<uint8_t>((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
}

// Values 128..16383 as a protobuf varint: two bytes.
void put(std::vector<uint8_t> &data, size_t offset, int was, int value)
{
    require(value >= 128 && value <= 16383, "Size outside what a Core ML template can take");
    require(offset + 2 <= data.size() && data[offset] == (uint8_t)((was & 0x7F) | 0x80) && data[offset + 1] == (uint8_t)(was >> 7),
            "Core ML template and its size table do not match");
    data[offset] = (uint8_t)((value & 0x7F) | 0x80);
    data[offset + 1] = (uint8_t)(value >> 7);
}

} // namespace

void write_coreml_package(const std::string &models_dir, const std::string &model, int width, int height,
                          const std::string &destination)
{
    namespace fs = std::filesystem;
    require(width % 2 == 0 && height % 2 == 0 && width >= kCoreMLMinSide && height >= kCoreMLMinSide
            && width <= kCoreMLMaxSide && height <= kCoreMLMaxSide, "Tile size outside what a Core ML template can take");
    const fs::path source = fs::path(models_dir) / (model + ".mlpackage");
    require(fs::is_directory(source), "Core ML model not found: " + source.string());
    const Table t = read_table(fs::path(models_dir) / (model + ".mlpatch"));
    std::vector<uint8_t> spec = read_all(source / t.model_path);
    require(spec.size() == t.model_size, "Core ML template and its size table do not match");
    const std::map<std::string, std::pair<int, int>> values = {
        {"h", {t.template_h, height}}, {"w", {t.template_w, width}},
        {"h2", {t.template_h / 2, height / 2}}, {"w2", {t.template_w / 2, width / 2}},
        {"hh", {t.template_h * 2, height * 2}}, {"ww", {t.template_w * 2, width * 2}}};
    for (const auto &kind : t.offsets) {
        auto found = values.find(kind.first);
        require(found != values.end(), "Unknown size kind in the Core ML size table: " + kind.first);
        for (size_t offset : kind.second) put(spec, offset, found->second.first, found->second.second);
    }
    std::error_code error;
    fs::remove_all(destination, error);
    fs::create_directories(destination);
    // Everything but the model description is the template's (the weights do not depend on the size).
    fs::copy(source, destination, fs::copy_options::recursive | fs::copy_options::overwrite_existing);
    std::ofstream out(fs::path(destination) / t.model_path, std::ios::binary | std::ios::trunc);
    out.write((const char *)spec.data(), (std::streamsize)spec.size());
    require(out.good(), "Could not write the Core ML model to " + destination);
}

std::string coreml_template_tag(const std::string &models_dir, const std::string &model)
{
    // Includes all package resources, especially the external weights. v2 is a
    // new namespace: older compiled caches stay on disk but cannot be reused.
    namespace fs = std::filesystem;
    const fs::path table_path = fs::path(models_dir) / (model + ".mlpatch");
    const Table t = read_table(table_path);
    const fs::path package = fs::path(models_dir) / (model + ".mlpackage");
    require(fs::is_regular_file(package / t.model_path), "Core ML model description missing: " + (package / t.model_path).string());
    auto resources = identity::tree(package, "package/");
    resources.emplace_back("table", table_path);
    return "v2-" + identity::files("coreml-native-template-v2", std::move(resources));
}

} // namespace aji
