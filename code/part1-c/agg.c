struct Point { int x; int y; };
struct Mixed { char c; int i; double d; };

int get_y(struct Point *p) { return p->y; }
void set_x(struct Point *p, int v) { p->x = v; }
int sum_arr(int *a, int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
