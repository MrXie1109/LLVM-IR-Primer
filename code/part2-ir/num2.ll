define i32 @f(i32 %a) {
  %x = add i32 %a, 1
  br label %2

2:
  ret i32 %x
}
