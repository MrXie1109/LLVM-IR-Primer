int abs_v(int x) {
    if (x < 0)
        return -x;
    return x;
}
int sum_to(int n) {
    int s = 0;
    for (int i = 1; i <= n; i++)
        s += i;
    return s;
}
int classify(int x) {
    if (x < 0) return -1;
    else if (x == 0) return 0;
    else return 1;
}
