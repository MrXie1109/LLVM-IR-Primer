define i32 @f(i32 %a, i32 %b) {
entry:
  %c = icmp sgt i32 %a, %b
  br i1 %c, label %t, label %f
t:
  br label %m
f:
  br label %m
m:
  %r = phi i32 [ %a, %t ], [ %b, %entry ]
  ret i32 %r
}
