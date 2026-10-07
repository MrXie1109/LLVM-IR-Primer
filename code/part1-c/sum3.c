/* 第 11 章：浮点 fast-math 标志。
   用 -ffast-math 编译，fadd 会带上 fast 标志。 */
double sum3(double a, double b, double c) { return a + b + c; }
