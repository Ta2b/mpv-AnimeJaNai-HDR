#pragma once
#include "cache_io.h"
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace aji::cache {
inline void mark_stage(const std::filesystem::path &folder, const std::string &key)
{
    std::ofstream file(folder / ".aji-stage-owner", std::ios::binary);
    file << "aji-stage-owner-v1\n" << key << '\n'; file.close();
    if (!file) throw io_error("record cache staging ownership",folder/".aji-stage-owner");
}
inline bool owns_stage(const std::filesystem::path &folder, const std::string &key)
{
    if (std::filesystem::is_symlink(folder) ||
        std::filesystem::is_symlink(folder / ".aji-stage-owner")) return false;
    std::ifstream file(folder / ".aji-stage-owner", std::ios::binary);
    std::string version, stored, extra;
    return std::getline(file, version) && version == "aji-stage-owner-v1" &&
           std::getline(file, stored) && stored == key && !std::getline(file, extra) &&
           file.eof() && !file.bad();
}
inline bool has_owned_stages(const std::filesystem::path &parent, const std::string &prefix,
                             const std::string &key)
{
    for (const auto &entry : std::filesystem::directory_iterator(parent))
        if (entry.path().filename().u8string().rfind(prefix, 0) == 0 && owns_stage(entry.path(), key))
            return true;
    return false;
}
// Caller holds the matching key lock, and creates new stages only after
// acquiring it. Thus any previous stage owned by this key is orphaned.
inline void recover_owned_stages(const std::filesystem::path &parent, const std::string &prefix,
                                 const std::string &key)
{
    for (const auto &entry : std::filesystem::directory_iterator(parent))
        if (entry.path().filename().u8string().rfind(prefix, 0) == 0 && owns_stage(entry.path(), key))
        {
            std::string why;
            if (!cleanup_stage(entry.path(),&why)) throw std::runtime_error(why);
        }
}
}
