#pragma once
#include <cerrno>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <system_error>
#ifndef _WIN32
#include <unistd.h>
#endif

namespace aji::cache {
inline std::string io_message(const char *operation, const std::filesystem::path &path,
                              std::error_code error)
{
    if (!error) error=std::make_error_code(std::errc::io_error);
    std::string hint=" Check cache storage and reopen the video to retry.";
    if (error==std::errc::permission_denied || error==std::errc::read_only_file_system)
        hint=" Restore cache access permissions or use writable storage, then reopen the video.";
    bool full=error==std::errc::no_space_on_device;
#ifdef EDQUOT
    full=full || error==std::error_code(EDQUOT,std::generic_category());
#endif
    if (full) hint=" Free cache space or quota, then reopen the video to retry.";
    return std::string(operation)+": "+path.u8string()+": "+error.message()+hint;
}
inline std::runtime_error io_error(const char *operation, const std::filesystem::path &path,
                                   std::error_code error={errno,std::generic_category()})
{
    return std::runtime_error(io_message(operation,path,error));
}
inline bool cleanup_stage(const std::filesystem::path &folder, std::string *why=nullptr)
{
    if (folder.empty()) return true;
#ifndef _WIN32
    // Keep the ownership marker/data intact if the directory itself cannot
    // be removed. A later request can recover it after permissions return.
    if (::access(folder.parent_path().c_str(),W_OK)!=0 && (errno==EACCES || errno==EROFS)) {
        if (why) *why=io_message("remove staging",folder,{errno,std::generic_category()});
        return false;
    }
#endif
    std::error_code error;std::filesystem::remove_all(folder,error);
    if (error && why) *why=io_message("remove staging",folder,error);
    return !error;
}
}
