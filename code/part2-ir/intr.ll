declare void @llvm.memcpy.p0.p0.i64(ptr, ptr, i64, i1)
declare void @llvm.memset.p0.i64(ptr, i8, i64, i1)
declare i32 @llvm.ctpop.i32(i32)
declare i32 @llvm.smax.i32(i32, i32)
declare void @llvm.trap()

define void @demo(ptr %d, ptr %s, i32 %x) {
  call void @llvm.memcpy.p0.p0.i64(ptr %d, ptr %s, i64 16, i1 false)
  call void @llvm.memset.p0.i64(ptr %d, i8 0, i64 16, i1 false)
  %p = call i32 @llvm.ctpop.i32(i32 %x)
  %m = call i32 @llvm.smax.i32(i32 %x, i32 %p)
  ret void
}
