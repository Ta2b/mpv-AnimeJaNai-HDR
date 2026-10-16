#include "surface.h"
#include <stdio.h>
int main(void) {
    printf("{\"surface\":%zu,\"caps\":%zu,\"color\":%zu,\"planes\":%zu,\"owner\":%zu,\"pts\":%zu}\n",
        sizeof(aji_surface_v1),sizeof(aji_surface_caps_v1),offsetof(aji_surface_v1,color),
        offsetof(aji_surface_v1,planes),offsetof(aji_surface_v1,owner),offsetof(aji_surface_v1,pts));
}
