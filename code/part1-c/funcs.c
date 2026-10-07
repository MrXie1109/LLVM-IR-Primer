int add(int, int);
int call_add(int a, int b) { return add(a, b); }
int apply(int (*f)(int,int), int a, int b) { return f(a, b); }
static int helper(int x) { return x * 3; }
int use_helper(int x) { return helper(x); }
int fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }
