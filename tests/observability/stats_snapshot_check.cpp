// One bounded before/after sequence: cadence, concurrent readers, error preservation.
#include "../../native/common/stats_snapshot.h"
#include <thread>
#include <iterator>
#include <iostream>
#include <cassert>
namespace fs=std::filesystem;
std::string read(const fs::path &p) {
    std::ifstream f(p,std::ios::binary);
    return {std::istreambuf_iterator<char>(f),{}};
}
int main(int argc,char **argv) {
    assert(argc==2);const fs::path root=fs::u8path(argv[1]);fs::create_directories(root);
    for (bool bounded : {false,true}) {
        const auto file=root/(bounded?"after.txt":"before.txt");
        aji::StatsPublisher publisher;
        uint64_t writes=0,bytes=0;std::atomic<uint64_t> reads{0},incomplete{0};
        std::atomic<bool> stop{false};
        auto payload=[](int n) { const auto id=std::to_string(n);return "BEGIN "+id+"\n"+std::string(128*1024,'x')+"\nEND "+id+"\n"; };
        auto publish=[&](int n,bool force) {
            auto render=[&] { auto s=payload(n);++writes;bytes+=s.size();return s; };
            if (bounded) publisher.publish(file.u8string(),render,force);
            else { std::ofstream f(file,std::ios::binary|std::ios::trunc);f<<render();f.close();assert(f); }
        };
        publish(-1,true);
        std::thread reader([&] {
            while(!stop) {
                const auto s=read(file);++reads;
                const auto e=s.find('\n');
                const auto id=e==std::string::npos?"?":s.substr(6,e-6);
                if (s.rfind("BEGIN ",0)!=0 || s.find("\nEND "+id+"\n")==std::string::npos) ++incomplete;
                std::this_thread::yield();
            }
        });
        const auto started=std::chrono::steady_clock::now();
        for (int i=0;i<300;++i) { publish(i,i==0);std::this_thread::sleep_for(std::chrono::microseconds(1850)); }
        publish(300,true);stop=true;reader.join();
        assert(read(file).find("END 300\n")!=std::string::npos);
        if(bounded) { assert(writes>=4 && writes<=6);assert(incomplete==0); }
        std::cout<<(bounded?"after":"before")<<" writes="<<writes<<" payload_bytes="<<bytes<<" reads="<<reads
            <<" incomplete="<<incomplete<<" elapsed_ms="<<std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count()<<"\n";
    }
    const auto dir=root/"readonly";fs::create_directory(dir);const auto file=dir/"stats.txt";
    { std::ofstream f(file);f<<"previous complete\n"; }
    fs::permissions(dir,fs::perms::owner_read|fs::perms::owner_exec);
    aji::StatsPublisher p;assert(!p.publish(file.u8string(),[]{return "new\n";},true));
    assert(read(file)=="previous complete\n");
    fs::permissions(dir,fs::perms::owner_all);
    assert(p.publish(file.u8string(),[]{return "recovered\n";},true));
    assert(read(file).rfind("recovered\n",0)==0);
    for(const auto &f:fs::directory_iterator(root))assert(f.path().filename().u8string().rfind(".aji-stats-",0)!=0);
    std::cout<<"error_preserves_old=1 recovery=1 final_complete=1\n";
}
