// Diagnostic state only: it never owns an executor/context or pixel buffers.
#pragma once
#include <algorithm>
#include <memory>
#include <mutex>
#include <string>
#include <tuple>
#include <vector>

namespace aji::detail {
enum class PlacementStatus { Pending, Ready, Unavailable, Failed, Disabled };
struct PlacementSnapshot { PlacementStatus status;std::string message; };
class PlacementState {
    mutable std::mutex mutex;
    PlacementStatus status;
    std::string message;
public:
    explicit PlacementState(PlacementStatus value=PlacementStatus::Pending,std::string text="pending (asynchronous compute plan)")
        :status(value),message(std::move(text)){}
    PlacementSnapshot snapshot() const {std::lock_guard<std::mutex> lock(mutex);return {status,message};}
    void complete(PlacementStatus value,std::string text) {
        std::lock_guard<std::mutex> lock(mutex);
        if(status!=PlacementStatus::Pending)return;
        status=value;message=std::move(text);
    }
};
struct PlacementKey {
    std::string template_content,model,os_build;
    int width=0,height=0,units=0,low_precision=0,reshape=-1,specialization=-1;
    bool operator==(const PlacementKey &other) const {
        return std::tie(template_content,model,os_build,width,height,units,low_precision,reshape,specialization)
            ==std::tie(other.template_content,other.model,other.os_build,other.width,other.height,other.units,other.low_precision,other.reshape,other.specialization);
    }
};
class PlacementCache {
    struct Entry {PlacementKey key;std::shared_ptr<PlacementState> state;};
    std::mutex mutex;std::vector<Entry> entries;const size_t capacity;
    std::shared_ptr<PlacementState> full=std::make_shared<PlacementState>(PlacementStatus::Unavailable,"unavailable (diagnostic capacity reached)");
public:
    struct Request {std::shared_ptr<PlacementState> state;bool start;};
    explicit PlacementCache(size_t limit):capacity(limit){entries.reserve(limit);}
    Request get(const PlacementKey &key) {
        std::lock_guard<std::mutex> lock(mutex);
        for(const auto &entry:entries)if(entry.key==key)return {entry.state,false};
        if(entries.size()>=capacity) {
            // Never evict pending requests: otherwise a hung provider could
            // cause unbounded duplicate calls after repeated reconfiguration.
            auto old=std::find_if(entries.begin(),entries.end(),[](const Entry &entry){return entry.state->snapshot().status!=PlacementStatus::Pending;});
            if(old==entries.end())return {full,false};
            entries.erase(old);
        }
        auto state=std::make_shared<PlacementState>();entries.push_back({key,state});return {state,true};
    }
};
}
