define i32 @f(i32* %p) {
  %v = load i32, ptr %p
  ret i32 %v
}
