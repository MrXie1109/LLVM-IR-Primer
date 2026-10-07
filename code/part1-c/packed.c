struct __attribute__((packed)) P { char c; int i; };
int get_i(struct P *p) { return p->i; }
