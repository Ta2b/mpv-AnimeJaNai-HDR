#include "model_identity.h"
#include "cache_key_lock.h"
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>

int main(int argc,char **argv)
{
    if (argc!=2) return 2;
    namespace fs=std::filesystem;
    const auto folder=fs::u8path(argv[1]),final=folder/"reference.engine";
    { std::ofstream file(final);file << "REFERENCE"; }
    aji::cache::PendingEngine pending;
    bool published=false,owner=false;
    std::string why;
    {
    aji::cache::KeyLock lock(fs::u8path(final.u8string()+".key-lock"));
    pending=aji::cache::begin_engine(final);
    { std::ofstream file(pending.path);file << "REPLACEMENT"; }
    const auto permissions=fs::status(folder).permissions();
    fs::permissions(folder,fs::perms::owner_read|fs::perms::owner_exec,fs::perm_options::replace);
#ifdef AJI_ERROR_DETAIL
    published=aji::cache::finish_engine(pending,final,true,&why);
#else
    published=aji::cache::finish_engine(pending,final,true);
#endif
    owner=fs::is_regular_file(fs::u8path(pending.directory)/".aji-stage-owner");
    fs::permissions(folder,permissions,fs::perm_options::replace);
    }
    aji::cache::recover_engine(final);
    std::ifstream file(final);std::string reference;file >> reference;
    std::cout << std::boolalpha << "{\"published\":" << published
              << ",\"owner_preserved\":" << owner
              << ",\"stage_remains\":" << fs::exists(fs::u8path(pending.directory))
              << ",\"reference\":" << std::quoted(reference)
              << ",\"error\":" << std::quoted(why) << "}\n";
}
