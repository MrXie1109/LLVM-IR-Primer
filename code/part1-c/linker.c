extern int g_ext;
int read_ext(void) { return g_ext; }
extern int other(int);
int call_other(int x) { return other(x) + 1; }
