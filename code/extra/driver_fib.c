/* 第 19 章：调用编译器生成的 fib。
   生成：cd code/part3-lispc && python3 compiler.py examples/fib.lisp > fib.ll
         llvm-as-18 fib.ll -o fib.bc
   运行：clang-18 -w driver_fib.c fib.bc -o fibtest && ./fibtest */
#include <stdio.h>
int l_fib(int);
int main(void) {
    for (int i = 0; i < 10; i++) printf("fib(%d)=%d\n", i, l_fib(i));
    return 0;
}
