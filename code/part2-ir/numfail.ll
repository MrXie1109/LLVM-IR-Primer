; 附录 C.5 / 第 8 章：编号值倒退的真实报错。
; 这里 %4 出现在 %6 之后 —— LLVM 的编号计数器不允许倒退。
; 预期：llvm-as-18 报 "label expected to be numbered '7' or greater"
define i32 @l_ack(i32 %m, i32 %n) {
entry:
  %1 = icmp eq i32 %m, 0
  br i1 %1, label %2, label %3
2:
  %6 = add i32 %n, 1
  ret i32 %6
3:
  %4 = sub i32 %m, 1
  ret i32 %4
}
