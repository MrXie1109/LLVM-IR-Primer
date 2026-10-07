/* 第 4 章：为什么 -O2 不能把 && 折叠成 and i1 —— 因为 b 有副作用。 */
int f(void);
int a_side_effect(int a) { return a && f(); }
