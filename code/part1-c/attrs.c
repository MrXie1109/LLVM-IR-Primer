__attribute__((noinline)) int noinline_f(int x) { return x; }
__attribute__((always_inline)) static inline int always_f(int x) { return x + 1; }
__attribute__((noreturn)) void die(void) { __builtin_trap(); }
int use_inline(int x) { return always_f(x); }
