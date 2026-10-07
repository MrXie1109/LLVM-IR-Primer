/* 第 12 章：测试 llvm.sadd.with.overflow.i32 的溢出检测。 */
#include <stdio.h>
#include <limits.h>
int safe_add(int, int);
int main(void) {
    printf("%d %d\n", safe_add(2, 3), safe_add(INT_MAX, 1));
    return 0;
}
