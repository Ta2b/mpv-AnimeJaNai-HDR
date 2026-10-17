// macOS Core ML directory artifacts: immutable generations and one atomic commit.
// Also compiled on POSIX hosts by the protocol fixture. No ML/GPU dependency.
#pragma once
#include "../common/cache_key_lock.h"
#include "../common/cache_stage_owner.h"
#include <atomic>
#include <chrono>
#include <fstream>
#include <functional>
#include <iostream>
#include <fcntl.h>
#include <unistd.h>

namespace aji::coreml::cache {
namespace fs = std::filesystem;
inline std::string nonce()
{
    static std::atomic<unsigned long long> sequence{0};
    return std::to_string(::getpid()) + "-" +
        std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "-" +
        std::to_string(sequence.fetch_add(1));
}
inline bool generation_name(const std::string &value)
{
    return value.size() > 5 && value.size() < 100 && value.compare(0,5,"data-") == 0 &&
        value.find_first_not_of("0123456789-",5) == std::string::npos &&
        value.find_first_of("0123456789",5) != std::string::npos;
}
inline void sync_path(const fs::path &path)
{
    int fd = ::open(path.c_str(),O_RDONLY | O_CLOEXEC);
    if(fd < 0) throw aji::cache::io_error("open Core ML cache for flush",path);
    int result = ::fsync(fd), saved = errno; ::close(fd);
    if(result) throw aji::cache::io_error("flush Core ML cache",path,{saved,std::generic_category()});
}
inline void sync_tree(const fs::path &folder)
{
    // Children before parents. Refuse links/special files rather than syncing
    // unrelated storage through a directory artifact.
    for(const auto &entry:fs::directory_iterator(folder)) {
        if(entry.is_symlink()) throw std::runtime_error("Core ML compiled cache contains a link: "+entry.path().string());
        if(entry.is_directory()) sync_tree(entry.path());
        else if(entry.is_regular_file()) sync_path(entry.path());
        else throw std::runtime_error("Core ML compiled cache contains a special file: "+entry.path().string());
    }
    sync_path(folder);
}
struct Entry {
    fs::path directory;
    std::string generation;
    fs::path compiled() const {return directory/generation/"model.mlmodelc";}
    explicit operator bool() const {return !generation.empty();}
};
class Store {
    fs::path directory_;
    std::string key_;
    Entry read() const
    {
        const auto pointer=directory_/"current";
        const auto status=fs::symlink_status(pointer);
        if(status.type()==fs::file_type::not_found) return {directory_,{}};
        if(!fs::is_regular_file(status) || fs::file_size(pointer)>256)
            throw std::runtime_error("Core ML cache commit is not an owned record: "+pointer.string());
        std::ifstream file(pointer,std::ios::binary);
        std::string version,key,generation,extra;
        if(!std::getline(file,version) || version!="aji-coreml-cache-tx1" ||
           !std::getline(file,key) || key!=key_ || !std::getline(file,generation) ||
           !generation_name(generation) || std::getline(file,extra) || !file.eof() || file.bad() ||
           !fs::is_directory(directory_/generation) || !aji::cache::owns_stage(directory_/generation,key_))
            throw std::runtime_error("Core ML cache commit malformed or generation unowned; preserved: "+pointer.string());
        if(fs::is_symlink(directory_/generation/"model.mlmodelc"))
            throw std::runtime_error("Core ML compiled artifact is a link; preserved: "+pointer.string());
        return {directory_,generation};
    }
    void writable_directory() const
    {
        fs::create_directories(directory_);
        if(fs::is_symlink(directory_) || fs::is_symlink(directory_/"lock"))
            throw std::runtime_error("Core ML cache key directory/lock must not be a link: "+directory_.string());
    }
public:
    Store(const fs::path &cache_root,const std::string &program):key_("p3-"+program)
    {
        if(program.size()!=64 || program.find_first_not_of("0123456789abcdef")!=std::string::npos)
            throw std::runtime_error("Core ML cache requires a SHA256 program key");
        directory_=cache_root/"native"/"coreml-tx1"/program;
    }
    Entry acquire(const std::function<void(const fs::path &)> &build) const try
    {
        // Complete hits need neither write access nor a write lock. Readers
        // keep a stable URL even after another process retires its commit.
        if(fs::is_symlink(directory_)) throw std::runtime_error("Core ML cache key directory is a link");
        auto hit=read(); if(hit) return hit;
        writable_directory();
        aji::cache::KeyLock lock(directory_/"lock");
        hit=read(); if(hit) return hit;
        aji::cache::recover_owned_stages(directory_,".stage-",key_);
        const auto id=nonce();
        const auto stage=directory_/(".stage-"+id);
        if(!fs::create_directory(stage)) throw std::runtime_error("Core ML staging collision: "+stage.string());
        try {
            aji::cache::mark_stage(stage,key_);
            build(stage); // Must natively validate model.mlmodelc before returning.
            if(!fs::is_directory(stage/"model.mlmodelc")) throw std::runtime_error("Core ML builder returned no compiled directory");
            const std::string generation="data-"+id;
            std::ofstream pointer(stage/".commit",std::ios::binary);
            pointer << "aji-coreml-cache-tx1\n" << key_ << '\n' << generation << '\n'; pointer.close();
            if(!pointer) throw aji::cache::io_error("write Core ML cache commit",stage/".commit");
            sync_tree(stage);
            fs::rename(stage,directory_/generation);
            sync_path(directory_);
            // POSIX rename replaces the small record, never a directory that
            // Core ML/MLComputePlan may still use. The generation stays put.
            fs::rename(directory_/generation/".commit",directory_/"current");
            sync_path(directory_);
            return {directory_,generation};
        } catch(...) {
            if(aji::cache::owns_stage(stage,key_)) {
                std::string why;
                if(!aji::cache::cleanup_stage(stage,&why)) std::cerr << "[aji] " << why << '\n';
            }
            throw;
        }
    }
    catch(const fs::filesystem_error &error) {
        throw aji::cache::io_error("Core ML cache transaction",error.path1(),error.code());
    }
    void retire(const Entry &failed) const try
    {
        writable_directory();
        aji::cache::KeyLock lock(directory_/"lock");
        const auto current=read();
        if(current.generation!=failed.generation) return; // A concurrent repair won.
        if(!current) return;
        fs::rename(directory_/"current",directory_/("retired-"+nonce()));
        sync_path(directory_);
        // Retain the entire generation, including native artifacts and ownership.
        // GC would require reader/diagnostic leases and is deliberately separate.
    }
    catch(const fs::filesystem_error &error) {
        throw aji::cache::io_error("retire Core ML cache commit",error.path1(),error.code());
    }
};
} // namespace aji::coreml::cache
