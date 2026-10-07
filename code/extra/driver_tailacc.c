/* 第 15 章：尾递归实验。注意 -O0 下深递归会栈溢出（段错误），
   经 -O2 后 LLVM 把尾递归变成循环，一百万也能算对。 */
#include <stdio.h>
#include <stdlib.h>
int l_sum_acc(int, int);
int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 100;
    printf("sum_acc(%d,0) = %d\n", n, l_sum_acc(n, 0));
    return 0;
}
