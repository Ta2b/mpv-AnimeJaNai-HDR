#include "placement_diagnostic.h"
#include <cassert>
#include <functional>
#include <iostream>
#include <thread>
using namespace aji::detail;
int main() {
    PlacementKey key;key.template_content="sha-model1";key.width=256;key.height=256;
    PlacementCache cache(1);auto a=cache.get(key),duplicate=cache.get(key);
    assert(a.start&&!duplicate.start&&a.state==duplicate.state);
    assert(a.state->snapshot().status==PlacementStatus::Pending);
    auto different=key;different.template_content="sha-model2";
    auto limited=cache.get(different);assert(!limited.start&&limited.state->snapshot().status==PlacementStatus::Unavailable);
    assert(cache.get(key).state==a.state); // pending entry wasn't evicted
    std::thread callback([state=a.state]{state->complete(PlacementStatus::Ready,"plan obtained");});
    auto concurrent=a.state->snapshot();assert(concurrent.status==PlacementStatus::Pending||concurrent.status==PlacementStatus::Ready);
    callback.join();assert(a.state->snapshot().message=="plan obtained");
    auto next=cache.get(different);assert(next.start&&next.state!=a.state);
    assert(a.state->snapshot().status==PlacementStatus::Ready); // evicted reader remains safe
    next.state->complete(PlacementStatus::Failed,"diagnostic failure");
    assert(next.state->snapshot().status==PlacementStatus::Failed);
    next.state->complete(PlacementStatus::Ready,"duplicate callback ignored");
    assert(next.state->snapshot().message=="diagnostic failure");
    std::function<void()> late;std::weak_ptr<PlacementState> lifetime;
    {PlacementCache temporary(1);auto request=temporary.get(key);lifetime=request.state;
     late=[state=request.state]{state->complete(PlacementStatus::Ready,"late completion");};}
    assert(!lifetime.expired());late();assert(lifetime.lock()->snapshot().message=="late completion");late={};assert(lifetime.expired());
    PlacementCache identities(4);
    auto base=identities.get(key);auto geometry=key;geometry.width=512;
    auto precision=key;precision.low_precision=1;
    assert(identities.get(geometry).state!=base.state&&identities.get(precision).state!=base.state);
    PlacementCache disabled_capacity(0);assert(!disabled_capacity.get(key).start);
    std::cout<<"placement_diagnostic_check: pending/ready/error, dedup, bound, key, late callback and concurrent snapshot passed\n";
}
