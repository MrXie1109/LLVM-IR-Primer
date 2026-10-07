# Chapter 3 Arithmetic, Logic and Shifts

In the previous chapter we only looked at multiplication and addition. This chapter goes through the whole landscape of integer operations, focusing on **which IR instruction each operator corresponds to, and why some carry `nsw` while others do not**.

All the IR in this chapter comes from the same set of C functions, generated with `clang-18 -S -emit-llvm -O2`. `-O2` is chosen because it makes the correspondence "one C operation = one IR instruction" clearest; the `-O0` version merely adds a layer of `alloca`/`load`/`store`, which you can compare yourself by running `-O0`.

## 3.1 Binary integer operations

```c
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int mul(int a, int b) { return a * b; }
int sdiv(int a, int b) { return a / b; }
int udiv(unsigned a, unsigned b) { return a / b; }
int srem(int a, int b) { return a % b; }
int urem(unsigned a, unsigned b) { return a % b; }
```

The corresponding IR:

```llvm
define dso_local i32 @add(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = add nsw i32 %1, %0
  ret i32 %3
}

define dso_local i32 @sub(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = sub nsw i32 %0, %1
  ret i32 %3
}

define dso_local i32 @mul(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = mul nsw i32 %1, %0
  ret i32 %3
}

define dso_local noundef i32 @sdiv(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = sdiv i32 %0, %1
  ret i32 %3
}

define dso_local noundef i32 @udiv(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = udiv i32 %0, %1
  ret i32 %3
}

define dso_local noundef i32 @srem(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = srem i32 %0, %1
  ret i32 %3
}

define dso_local noundef i32 @urem(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = urem i32 %0, %1
  ret i32 %3
}
```

### Signed and unsigned are **two different instructions**

This is one of the most important design decisions in LLVM IR.

In C, `a / b` has only one spelling, and its meaning depends on the **types** of `a` and `b`. In IR, **the type does not determine the semantics of the operation** — `i32` means neither "signed" nor "unsigned"; it is just a 32-bit integer. How the division is actually done is decided by the **instruction name**:

| C spelling | IR instruction | Semantics |
|---|---|---|
| `int a / int b` | `sdiv` | Signed division (rounds toward zero) |
| `unsigned a / unsigned b` | `udiv` | Unsigned division |
| `int a % int b` | `srem` | Signed remainder |
| `unsigned a % unsigned b` | `urem` | Unsigned remainder |

**Why design it this way?** Because at the hardware level these are two different instructions to begin with. x86-64's `idiv` and `div` are two opcodes, and ARM's `sdiv` and `udiv` likewise. If signedness were written into the type system, the back end would have to translate the type into an instruction every time; better to let the front end make the decision directly.

On what basis can the front end make that decision? Because C's type system **already has** this information — clang knows perfectly well whether `a` is `int` or `unsigned`; it merely moves that information from "the type" to "the instruction name."

This also explains why in real IR you **never see** a distinction between `i32` and `u32`: there is simply no such concept as an "unsigned integer type" in LLVM.

### Why does division have no `nsw`?

Look back: `add`, `sub`, and `mul` all carry `nsw`, while `sdiv`, `udiv`, `srem`, and `urem` carry none.

The reason is that `nsw` describes the behaviour **on overflow**, and division does not overflow at all (the only exception is `INT_MIN / -1`, which is a different kind of UB expressed by a different mechanism). The danger with division is **division by zero**, and that needs no annotation in IR at all — **`sdiv`/`udiv` by zero produces `poison`**; that is the instruction's built-in semantics.

There is a distinction between "producing `poison`" and "undefined behaviour" that is worth spelling out: `poison` is a **value**, and it propagates along the data flow; only when it affects **observable behaviour** (say, as the condition of a `br`, or being `store`d to memory) does the program actually become UB. So:

```llvm
%r = sdiv i32 %a, 0        ; %r is poison
```

If `%r` is never used, nothing happens to the program at all. The optimizer will even eliminate the whole computation:

```bash
$ opt-18 -passes=instcombine -S dz.ll -o -
```

```llvm
define i32 @f(i32 %a) {
  ret i32 poison
}
```

**This mechanism of "poison rather than immediate UB" is exactly what allows flags like `nsw` and `inbounds` to license aggressive optimization** (Chapter 10 covers the difference between `poison` and `undef` in detail).

Also note the extra `noundef` in `dso_local noundef i32 @sdiv`. This is a return value attribute, meaning the function guarantees not to return `undef`. `udiv` carries it too. Why does `add` not? This is a subtle judgement the optimizer makes based on usage, and it changes between versions. **Do not memorize attributes like these as if they were a fixed rule** — they are entirely at the optimizer's discretion.

## 3.2 Unary operations: `neg` and `bnot`

C has no "negate" instruction; `-a` is just `0 - a`:

```c
int neg(int a) { return -a; }
int bnot(int a) { return ~a; }
```

```llvm
define dso_local i32 @neg(i32 noundef %0) local_unnamed_addr #0 {
  %2 = sub nsw i32 0, %0
  ret i32 %2
}

define dso_local noundef i32 @bnot(i32 noundef %0) local_unnamed_addr #0 {
  %2 = xor i32 %0, -1
  ret i32 %2
}
```

Two details are worth noting:

1. **`sub nsw i32 0, %0`**: `0` is the **first operand** of `sub`. In IR, constants can appear directly as operands; there is no need for a preceding `%c = ...`.
2. **`xor i32 %0, -1`**: bitwise NOT is represented as "XOR with all ones." `-1` in binary is 32 ones. IR has **no** separate `not` instruction — this is deliberate, because `not x` is equivalent to `xor x, -1`, and one fewer instruction is one less piece of implementation and testing cost.

Incidentally, it is quite natural that `bnot` has no `nsw`: `xor` is a bitwise operation, and there is no notion of "overflow" for it.

## 3.3 Bitwise operations

```c
int land(int a, int b) { return a & b; }
int lor(int a, int b) { return a | b; }
int lxor(int a, int b) { return a ^ b; }
```

Note that I deliberately named these `land`/`lor` here, to avoid confusion with "logical and/logical or" — they are actually **bitwise** operations:

```llvm
define dso_local i32 @land(i32 noundef %0, i32 noundef %1) #0 {
  %3 = and i32 %1, %0
  ret i32 %3
}

define dso_local i32 @lor(i32 noundef %0, i32 noundef %1) #0 {
  %3 = or i32 %1, %0
  ret i32 %3
}

define dso_local i32 @lxor(i32 noundef %0, i32 noundef %1) #0 {
  %3 = xor i32 %1, %0
  ret i32 %3
}
```

One to one: `&` → `and`, `|` → `or`, `^` → `xor`. None of them use `nsw`; bitwise operations do not overflow.

> **Beware of a common confusion**: C's `&&` and `||` are **not** `and` and `or`. `&&` has short-circuit semantics (if the left side is false, the right side is not evaluated), so it must be implemented with `br` control flow. Chapter 5 covers this. The `&`, `|`, and `^` here are the bit-by-bit operations.

## 3.4 Shifts: three different instructions

```c
int shl(int a, int b) { return a << b; }
int ashr(int a, int b) { return a >> b; }
unsigned lshr(unsigned a, unsigned b) { return a >> b; }
```

```llvm
define dso_local i32 @shl(i32 noundef %0, i32 noundef %1) #0 {
  %3 = shl i32 %0, %1
  ret i32 %3
}

define dso_local i32 @ashr(i32 noundef %0, i32 noundef %1) #0 {
  %3 = ashr i32 %0, %1
  ret i32 %3
}

define dso_local i32 @lshr(i32 noundef %0, i32 noundef %1) #0 {
  %3 = lshr i32 %0, %1
  ret i32 %3
}
```

Three instructions, corresponding cleanly to three kinds of semantics:

| Instruction | Full name | Semantics | When it is produced |
|---|---|---|---|
| `shl` | shift left | Left shift, filling 0 on the right | `a << b` |
| `ashr` | **a**rithmetic **sh**ift **r**ight | Right shift, filling the **sign bit** on the left | `a >> b` for signed values |
| `lshr` | **l**ogical **sh**ift **r**ight | Right shift, filling 0 on the left | `a >> b` for unsigned values |

The difference between `ashr` and `lshr` is exactly the difference in C between "signed right shift" and "unsigned right shift." Look at the result:

```c
int x = -8;
x >> 1     // signed: ashr, result is -4
```

```
-8 = 0xFFFFFFF8 = 1111...1111 1000
ashr 1  ->      1111...1111 1100 = -4     (sign bit filled with 1)
lshr 1  ->      0111...1111 1100 = 2147483644  (fills with 0)
```

The same bit sequence, the same `>>`, takes completely different instructions because of a difference in type, and produces completely different results. This once again shows: **signedness in IR is not reflected in the type, only in the instruction name.**

### Shifts have no `nsw`

Note that none of the three shifts carries `nsw`. A shift amount greater than or equal to the bit width is UB (`poison`), but that is not something the concept of "overflow" covers, so `nsw` does not apply.

## 3.5 One big table

| C operator | IR instruction | Carries `nsw`? | Notes |
|---|---|---|---|
| `a + b` | `add` | Yes when signed | |
| `a - b` | `sub` | Yes when signed | `-a` is written `sub nsw i32 0, %a` |
| `a * b` | `mul` | Yes when signed | |
| `a / b` (`int`) | `sdiv` | No | Division by zero produces `poison` |
| `a / b` (`unsigned`) | `udiv` | No | Division by zero produces `poison` |
| `a % b` (`int`) | `srem` | No | |
| `a % b` (`unsigned`) | `urem` | No | |
| `a & b` | `and` | No | |
| `a \| b` | `or` | No | |
| `a ^ b` | `xor` | No | `~a` is written `xor i32 %a, -1` |
| `a << b` | `shl` | No | |
| `a >> b` (signed) | `ashr` | No | Fills the sign bit |
| `a >> b` (unsigned) | `lshr` | No | Fills 0 |

## 3.6 What `nsw` is worth: an example

`nsw` is not decoration; it is a **licence for the optimizer**.

```c
int f(int x) {
    if (x + 1 > x) return 1;
    return 0;
}
```

Mathematically `x + 1 > x` always holds — but if `x` is `INT_MAX`, then `x + 1` is UB in C. Since the programmer guarantees that it will not happen, the compiler may assume it never happens. Measured with `-O2`:

```llvm
define dso_local noundef i32 @f(i32 noundef %0) local_unnamed_addr #0 {
  ret i32 1
}
```

**The whole function folds down to `ret i32 1`.** And with `-fwrapv` added (telling clang "overflow must wrap, it is not UB"), it becomes `icmp ne i32 %0, 2147483647` — the correct answer under wrapping semantics.

**The same C source, one compiler option, two utterly different pieces of IR and two different semantics.**

(For the role of `nsw` in strength reduction and division optimization, see [Appendix B.4](22-appendix-b-optimization-primer.md#b4-nsw-and-nuw-what-power-they-give-the-optimizer).)

## 3.7 Exercises

**Exercise 3.1** Generate the `unsigned` version of negation:

```c
unsigned uneg(unsigned a) { return -a; }
```

The actual output under `-O2` is:

```llvm
define dso_local noundef i32 @uneg(i32 noundef %0) local_unnamed_addr #0 {
  %2 = sub i32 0, %0
  ret i32 %2
}
```

The `nsw` **has disappeared**. Why? Because for unsigned values, "negation" is by definition subtraction modulo 2³², and wrapping is **defined behaviour**, not UB. Since it can never be poison, adding `nsw` would actually be wrong. Compare this with the `neg` of Section 3.2 (signed, carrying `nsw`) — the difference between these two pieces of IR is a complete projection of the difference in C semantics.

**Exercise 3.2** Write out the IR for `int shr_arith(int a) { return a >> 3; }` and `unsigned shr_log(unsigned a) { return a >> 3; }`, and confirm that they are `ashr` and `lshr` respectively.

**Exercise 3.3** Try the IR for `int p(int a) { return a * 2; }` under `-O2`. Do you expect to see `mul`? (Hint: shifting is faster than multiplying.) Then try `a * 3`, `a * 4`, `a * 5`.

**Exercise 3.4** Compile the `f` of Section 3.6 with `-fwrapv`:

```bash
clang-18 -S -emit-llvm -O2 -fwrapv f.c -o -
```

Compare whether `nsw` is present, and whether the function body is still folded into `ret i32 1`.

**Exercise 3.5** Hand-write a `.ll` file implementing `int clamp(int x, int lo, int hi)`, and verify your spelling directly with `llvm-as-18`, without using `-S`. (Chapter 11 gives a reference answer.)

## 3.8 Summary

- Signed and unsigned in IR are **not a difference in type but a difference in instruction**: `sdiv`/`udiv`, `srem`/`urem`, `ashr`/`lshr`.
- `nsw` = "signed overflow means poison," a licence for the optimizer, originating from C's UB rules.
- Division and shifts have no `nsw`: their problem is not overflow but division by zero or an out-of-range shift amount — such cases produce `poison` directly (see the next section).
- IR has no `not` instruction; negation is done with `xor x, -1`.
- `&&`/`||` are completely different from `&`/`|`; the former require control flow.

In the next chapter we look at comparison operations, and at that strange IR type `i1`.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 2 Your First IR: The Three-Line Truth About `mul_add`](02-ch02-your-first-ir-mul-add.md) · [Next: Chapter 4 Comparisons and the Tyranny of `i1` →](04-ch04-comparisons-and-i1.md)
