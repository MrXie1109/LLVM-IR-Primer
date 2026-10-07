define i32 @max_via_phi(i32 %a, i32 %b) {
entry:
  %c = icmp sgt i32 %a, %b
  br i1 %c, label %t, label %f
t:
  br label %m
f:
  br label %m
m:
  %r = phi i32 [ %a, %t ], [ %b, %f ]
  ret i32 %r
}

define i32 @loop_phi(i32 %n) {
entry:
  br label %head
head:
  %i = phi i32 [ 0, %entry ], [ %i.next, %body ]
  %acc = phi i32 [ 0, %entry ], [ %acc.next, %body ]
  %cond = icmp slt i32 %i, %n
  br i1 %cond, label %body, label %done
body:
  %acc.next = add i32 %acc, %i
  %i.next = add i32 %i, 1
  br label %head
done:
  ret i32 %acc
}
