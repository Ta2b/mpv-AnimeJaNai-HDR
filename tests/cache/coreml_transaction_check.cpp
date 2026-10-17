// Actual POSIX transaction protocol, including process exit/lock recovery.
#include "../../native/apple/coreml_cache_transaction.h"
#include <cassert>
#include <csignal>
#include <sys/wait.h>
using namespace aji::coreml::cache;
static void put(const fs::path &p,const std::string &s) {std::ofstream(p)<<s;}
static void artifact(const fs::path &stage) {fs::create_directory(stage/"model.mlmodelc");put(stage/"model.mlmodelc"/"model","valid");}
template<class F> void refused(F f) {bool failed=false;try{f();}catch(const std::exception&){failed=true;}assert(failed);}
int main(int argc,char **argv) {
    assert(argc==2);const fs::path root=argv[1];assert(!fs::exists(root));fs::create_directories(root);
    const std::string program(64,'a'),key="p3-"+program;Store store(root,program);
    const auto dir=root/"native"/"coreml-tx1"/program;
    fs::create_directories(dir/".stage-foreign");put(dir/".stage-foreign"/"keep","user");
    fs::create_directory(dir/".stage-owned");aji::cache::mark_stage(dir/".stage-owned",key);
    fs::create_directory(dir/".stage-other-key");aji::cache::mark_stage(dir/".stage-other-key","p3-other");
    bool built=false;
    const auto first=store.acquire([&](const auto &stage){built=true;artifact(stage);});
    assert(built && fs::is_regular_file(first.compiled()/"model"));
    assert(!fs::exists(dir/".stage-owned") && fs::exists(dir/".stage-foreign"/"keep") && fs::exists(dir/".stage-other-key"));
    const auto hit=store.acquire([](const auto&){assert(false);});assert(hit.generation==first.generation);
    // Invalid external records are preserved, never interpreted as filesystem paths.
    const auto record=dir/"current";fs::rename(record,dir/"saved-pointer");
    for(const auto &bad:{std::string("aji-coreml-cache-tx1\n")+key+"\n../outside\n",
                        std::string("aji-coreml-cache-tx1\np3-wrong\n")+first.generation+"\n",
                        std::string("aji-coreml-cache-tx1\n")+key+"\n"+first.generation+"\nextra\n"}) {
        put(record,bad);refused([&]{store.acquire(artifact);});assert(fs::file_size(record)==bad.size());fs::remove(record);
    }
    fs::create_symlink("saved-pointer",record);refused([&]{store.acquire(artifact);});assert(fs::is_symlink(record));fs::remove(record);
    fs::rename(dir/"saved-pointer",record);
    store.retire(first);assert(!fs::exists(record) && fs::exists(first.compiled()/"model"));
    // Errors before publication keep all prior generation data and no false hit.
    refused([&]{store.acquire([](const auto &stage){artifact(stage);throw std::runtime_error("build/validation failure");});});
    assert(!fs::exists(record) && fs::exists(first.compiled()/"model"));
    // Kill a real builder after ownership is recorded; kernel lock releases.
    int ready[2];assert(pipe(ready)==0);pid_t child=fork();assert(child>=0);
    if(child==0) {close(ready[0]);store.acquire([&](const auto &stage){artifact(stage);assert(write(ready[1],"x",1)==1);for(;;)pause();});_exit(2);}
    close(ready[1]);char byte;assert(read(ready[0],&byte,1)==1);close(ready[0]);assert(kill(child,SIGKILL)==0);int status;assert(waitpid(child,&status,0)==child && WIFSIGNALED(status));
    assert(aji::cache::has_owned_stages(dir,".stage-",key));
    const auto repaired=store.acquire(artifact);assert(repaired.generation!=first.generation);
    assert(!aji::cache::has_owned_stages(dir,".stage-",key) && fs::exists(first.compiled()/"model"));
    store.retire(first);assert(store.acquire([](const auto&){assert(false);}).generation==repaired.generation); // stale failure cannot retire repair
    // A complete hit works without mutation permissions. No builder/lock open.
    for(const auto &entry:fs::recursive_directory_iterator(dir))fs::permissions(entry.path(),entry.is_directory()?fs::perms::owner_read|fs::perms::owner_exec:fs::perms::owner_read);
    fs::permissions(dir,fs::perms::owner_read|fs::perms::owner_exec);
    assert(store.acquire([](const auto&){assert(false);}).generation==repaired.generation);
    std::cout << "PASS commit/strict-record/recovery/retained-generations/stale-retire/readonly\n";
}
