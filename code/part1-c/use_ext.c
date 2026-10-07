/* 第 6 章：extern 全局变量。
   只有真的使用 g_ext，生成的 IR 里才会出现 @g_ext 这一行。 */
extern int g_ext;
int use_ext(void) { return g_ext; }
