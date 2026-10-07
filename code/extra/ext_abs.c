/* 第 20 章：extern_call 测试用的外部函数实现。
   对应的 Lisp 源码是：
       (declare ext_abs (i32))
       (defn use_ext (x) (+ (ext_abs x) 1))
   函数名带 l_ 前缀，因为编译器会把 Lisp 函数名修饰成 l_<name>。 */
#include <stdlib.h>
int l_ext_abs(int x) { return abs(x); }
