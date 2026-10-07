; --- globals ---
@g = global i32 42, align 4
@c = constant i32 7, align 4
@arr = global [5 x i32] [i32 1, i32 2, i32 3, i32 4, i32 5], align 16
@str = private unnamed_addr constant [6 x i8] c"hello\00", align 1
@zeroinit = global [100 x i32] zeroinitializer, align 16
@ext = external global i32

; --- function attributes and linkage ---
define internal i32 @helper(i32 %x) {
  ret i32 %x
}

define dso_local i32 @pub(i32 %x) #0 {
  %r = call i32 @helper(i32 %x)
  ret i32 %r
}

declare i32 @printf(ptr, ...)

define i32 @uses_printf(ptr %fmt, i32 %v) {
  %r = call i32 (ptr, ...) @printf(ptr %fmt, i32 %v)
  ret i32 %r
}

define void @noreturn_fn() noreturn {
  unreachable
}

attributes #0 = { noinline nounwind }

!llvm.module.flags = !{!0}
!0 = !{i32 1, !"wchar_size", i32 4}
