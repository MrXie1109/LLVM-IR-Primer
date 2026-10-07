%struct.Point = type { i32, i32 }
%struct.Node  = type { i32, ptr }

define i32 @gep_demo(ptr %p, ptr %q, i64 %i) {
  ; struct field access: 0 then field index
  %f = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1
  %v = load i32, ptr %f
  ; array element: one index
  %e = getelementptr inbounds i32, ptr %q, i64 %i
  %w = load i32, ptr %e
  %s = add i32 %v, %w
  ret i32 %s
}

define ptr @gep_negative(ptr %base, i64 %i) {
  %r = getelementptr inbounds i32, ptr %base, i64 -1
  ret ptr %r
}
