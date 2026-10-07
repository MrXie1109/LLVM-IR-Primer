#include <stdatomic.h>
int test(volatile int *p, _Atomic int *a) {
    int v = *p;
    atomic_fetch_add(a, 1);
    return v;
}
