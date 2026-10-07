/* 第 9 章：查看结构体的实际布局（大小与字段偏移）。
   编译运行：clang-18 -w size_layout.c -o size && ./size */
#include <stdio.h>
#include <stddef.h>
struct Mixed { char c; int i; double d; };
struct __attribute__((packed)) Packed { char c; int i; };
int main(void) {
    printf("sizeof(struct Mixed) = %zu\n", sizeof(struct Mixed));
    printf("  c offset = %zu\n", offsetof(struct Mixed, c));
    printf("  i offset = %zu\n", offsetof(struct Mixed, i));
    printf("  d offset = %zu\n", offsetof(struct Mixed, d));
    printf("sizeof(packed) = %zu, offsetof(i) = %zu\n",
           sizeof(struct Packed), offsetof(struct Packed, i));
    return 0;
}
