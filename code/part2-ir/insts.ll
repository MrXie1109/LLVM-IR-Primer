define i32 @insts(i32 %a, i32 %b) {
  %x = add i32 %a, %b
  %y = sub i32 %a, %b
  %z = mul i32 %x, %y
  %q = sdiv i32 %z, %a
  %r = srem i32 %z, %b
  %s = shl i32 %q, 2
  %t = lshr i32 %s, 1
  %u = ashr i32 %t, 1
  %v = and i32 %u, 255
  %w = or i32 %v, 1
  %aa = xor i32 %w, 3
  %bb = icmp slt i32 %aa, 100
  %cc = select i1 %bb, i32 %aa, i32 0
  %dd = zext i1 %bb to i32
  %ee = add i32 %cc, %dd
  ret i32 %ee
}
