int g_counter = 42;
static int s_hidden = 7;
const int g_limit = 100;
extern int g_ext;

int get_counter(void) { return g_counter; }
void bump(void) { g_counter++; }
int* addr_of(void) { return &g_counter; }
