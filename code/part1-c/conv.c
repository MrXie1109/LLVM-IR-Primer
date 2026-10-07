long sext_it(int x) { return x; }
int trunc_it(long x) { return (int)x; }
unsigned zext_it(unsigned char c) { return c; }
int sitofp_it(int x) { return (int)(double)x; }
double uitofp_it(unsigned u) { return (double)u; }
unsigned fptoui_it(double d) { return (unsigned)d; }
int bitcast_test(int x) { return x; }
