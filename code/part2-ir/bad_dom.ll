define i32 @f(i32 %a, i1 %cond) {
entry:
  br i1 %cond, label %t, label %f
t:
  %x = add i32 %a, 1
  br label %m
f:
  br label %m
m:
  %y = add i32 %x, 1
  ret i32 %y
}
