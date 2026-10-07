void copy(int *restrict dst, const int *restrict src, int n) {
    for (int i = 0; i < n; i++) dst[i] = src[i];
}
