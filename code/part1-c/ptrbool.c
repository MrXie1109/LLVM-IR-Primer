int deref_or_zero(int *p) { return p ? *p : 0; }
int fcmp_ne(double a, double b) { return a != b; }
int ult_test(unsigned a, unsigned b) { return a >= b; }
int nan_test(double a) { return a != a; }
