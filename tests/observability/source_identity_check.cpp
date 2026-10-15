#include "../../native/common/source_identity.h"
#include <cassert>
#include <iostream>
int main() {
 aji::SourceKey key{1,2,128,72,401};assert(key.matches(key));
 auto view=key;view.stride++;assert(!key.matches(view));view=key;view.width++;assert(!key.matches(view));view=key;view.height++;assert(!key.matches(view));view=key;view.generation++;assert(!key.matches(view));
 assert(!key.matches({}));aji::SourceIdTracker t;
 assert(t.accept(1,1,2).current==2);assert(t.accept(1,1,2).current==2);
 assert(t.accept(1,2,3).current==3);
 assert(t.accept(1,0,1).current==0); // seek counter reset, generation forgotten
 assert(t.accept(1,3,4).current==0); // cannot resume trusting the recycled epoch
 assert(t.accept(2,0,1).current==1);assert(t.accept(1,3,4).current==0);
 assert(t.accept(0,0,0).current==0);assert(t.accept(2,1,2).current==2);
 assert(t.rejected_calls==3);
 std::cout<<"views, dimensions, generations, repeated pair, counter regression, stale epoch, legacy zero: PASS\n";
}
