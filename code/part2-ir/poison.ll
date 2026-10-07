define i32 @f(i1 %c) {
  %p = select i1 %c, i32 1, i32 poison
  %fr = freeze i32 %p
  ret i32 %fr
}
define i32 @u() {
  ret i32 undef
}
