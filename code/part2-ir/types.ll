; Every integer type LLVM has, and the aggregate types.
%struct.Point = type { i32, i32 }
%struct.Mixed = type { i8, i32, double }
%union.U = type { i64, [8 x i8] }

define void @demo() {
  %a = alloca i1
  %b = alloca i8
  %c = alloca i16
  %d = alloca i32
  %e = alloca i64
  %f = alloca i128
  %g = alloca half
  %h = alloca float
  %i = alloca double
  %j = alloca ptr
  %k = alloca [10 x i32]
  %l = alloca %struct.Point
  %m = alloca <4 x i32>
  ret void
}
