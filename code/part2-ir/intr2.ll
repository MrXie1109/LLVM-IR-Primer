declare i32 @llvm.ctpop.i32(i32)
declare i32 @llvm.smax.i32(i32, i32)

define i32 @ctpop_test(i32 %x) {
  %p = call i32 @llvm.ctpop.i32(i32 %x)
  ret i32 %p
}
define i32 @smax_test(i32 %a, i32 %b) {
  %m = call i32 @llvm.smax.i32(i32 %a, i32 %b)
  ret i32 %m
}
