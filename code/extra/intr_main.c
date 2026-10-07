/* 第 12 章：测试内建函数 llvm.ctpop / llvm.smax（对应 part2-ir/intr2.ll）。 */
#include <stdio.h>
int ctpop_test(int);
int smax_test(int, int);
int main(void) {
    printf("ctpop(255)=%d smax(3,9)=%d\n", ctpop_test(255), smax_test(3, 9));
    return 0;
}
