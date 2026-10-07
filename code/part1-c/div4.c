/* 附录 B.4：有符号除法不能变成移位（向零取整 vs 向下取整），
   无符号除法可以。 */
int div4(int a) { return a / 4; }
unsigned div4u(unsigned a) { return a / 4; }
