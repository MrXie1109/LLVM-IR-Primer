/* 第 12 章：restrict → noalias。
   注意 dst 是「既读又写」（dst[i] += a[i]），所以它的参数属性里
   有 noalias / nocapture 但【没有】writeonly —— 对比 restrict.c 里的
   copy（dst[i] = src[i]，只写），后者才有 writeonly。 */
void add_arrays(int *restrict dst, const int *restrict a, int n) {
    for (int i = 0; i < n; i++) dst[i] += a[i];
}
