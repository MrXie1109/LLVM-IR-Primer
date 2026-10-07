/* 第 5 章练习：调用生成/手写的 my_abs 或 loop_phi。 */
#include <stdio.h>
int loop_phi(int);
int main(void) {
    printf("loop_phi(10)  = %d\n", loop_phi(10));
    printf("loop_phi(100) = %d\n", loop_phi(100));
    return 0;
}
