/* 第 20 章用的 C 驱动：调用编译器生成的 sum_to 并打印结果。
   生成目标文件：cd code/part3-lispc && python3 compiler.py examples/sum.lisp > sum.ll
                 opt-18 -passes='default<O2>' -S sum.ll -o sum_O2.ll
                 llvm-as-18 sum_O2.ll -o sum_O2.bc
   编译运行：    clang-18 -w driver_sum.c sum_O2.bc -o sumtest && ./sumtest */
#include <stdio.h>
int l_sum_to(int);
int main(void) {
    printf("%d %d %d\n", l_sum_to(0), l_sum_to(10), l_sum_to(1000));
    return 0;
}
