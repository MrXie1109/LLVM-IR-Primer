# Chapter 11 The Instruction Reference

## 11.1 Referring back: that `zext i1 %3 to i32` from Chapter 4

In Chapter 4 we looked at `int lt(int a, int b) { return a < b; }`:

```llvm
  %3 = icmp slt i32 %0, %1
  %4 = zext i1 %3 to i32
```

At the time we said "`zext` is zero extension, widening the 1 of an `i1` into the 1 of an `i32`". This chapter goes through **all the instructions** systematically, including the family `zext` belongs to — **conversion instructions**.

At the same time this chapter answers a few questions left over from Part I:

- Why does an `i33` appear after the `sum_to` optimization? (→ `zext` and `trunc`, see [Appendix B.6](22-appendix-b-optimization-primer.md#b6-watching-pass-by-pass-a-complete-experiment))
- How do you choose between `select` and `phi`? (→ covered in Chapter 5, completed here)
- What other flags are there besides `inbounds`, `nsw`, `nuw`? (→ the "flag bits" scattered throughout)

## 11.2 The six categories of instructions

LLVM's instructions can be divided into six categories:

| Category | Instructions |
|---|---|
| **Terminators** | `ret`, `br`, `switch`, `indirectbr`, `invoke`, `callbr`, `resume`, `unreachable`, `catchswitch`, `catchret`, `cleanupret` |
| **Unary operations** | `fneg` |
| **Binary operations** | `add`, `sub`, `mul`, `udiv`, `sdiv`, `urem`, `srem`, `shl`, `lshr`, `ashr`, `and`, `or`, `xor`, `fadd`, `fsub`, `fmul`, `fdiv`, `frem` |
| **Bitwise operations** | see above (`and`/`or`/`xor`/`shl`/`lshr`/`ashr` also belong here) |
| **Memory access** | `alloca`, `load`, `store`, `fence`, `cmpxchg`, `atomicrmw`, `getelementptr` |
| **Conversions** | `trunc`, `zext`, `sext`, `fptrunc`, `fpext`, `fptoui`, `fptosi`, `uitofp`, `sitofp`, `ptrtoint`, `inttoptr`, `bitcast`, `addrspacecast` |
| **Other** | `icmp`, `fcmp`, `phi`, `select`, `call`, `va_arg`, `landingpad`, `freeze`, `extractelement`, `insertelement`, `shufflevector`, `extractvalue`, `insertvalue` |

Below we go through them category by category. **The point is not to memorize them but to understand why each category exists.**

## 11.3 Terminator instructions

**Every basic block must end with a terminator.** This is a hard syntactic requirement (measured in Chapter 14).

### `ret`

```llvm
ret void                  ; no return value
ret i32 %x                ; return a value
ret { i32, i32 } %pair    ; return an aggregate type
```

### `br`

```llvm
br label %target                        ; unconditional jump
br i1 %cond, label %t, label %f         ; conditional jump (the condition must be i1)
```

Covered in Chapter 5.

### `switch`

```llvm
switch i32 %x, label %default [
  i32 0, label %case0
  i32 1, label %case1
]
```

Covered in Chapter 5, including how it turns into a lookup table under `-O2`.

### `indirectbr`

```llvm
indirectbr ptr %addr, [label %a, label %b, label %c]
```

Jump to **one of a known set of targets**, decided by a runtime address. This exists to support C's computed goto (a GCC extension) and the main dispatch loop of an interpreter.

**Why is it needed?** Because an ordinary indirect jump makes the control flow unanalyzable for the optimizer. `indirectbr` lists all possible targets explicitly, so the optimizer knows which edges exist.

### `unreachable`

```llvm
unreachable
```

It means "reaching this point is impossible". In Chapter 7 we saw `noreturn` functions ending with it.

**Its optimization implications are strong**: if control flow reaches `unreachable`, the behaviour is undefined. The optimizer may therefore assume that "paths flowing into `unreachable` do not exist" and delete the condition checks that trigger those paths.

### Exception-related instructions

`invoke`, `landingpad`, `resume`, `catchswitch`, `catchret`, and `cleanupret` are used for exception handling and stack unwinding. This material is fairly complex, and our target language does not need exceptions, so this book does not go into it.

The only one worth mentioning is `invoke`:

```llvm
%r = invoke i32 @may_throw() to label %normal unwind label %exception
```

It is "a call that may throw": a normal return jumps to `%normal`, an exception jumps to `%exception`. **It is both a call and a terminator** — because the call may not return, so control flow forks here.

## 11.4 Binary operations and flags

Chapter 3 already covered integer arithmetic. Here we fill in the complete list of **flags**, because they are the optimizer's most important source of information.

### `nsw` / `nuw`

```llvm
%a = add nsw i32 %x, %y      ; no signed wrap: signed overflow makes it poison
%b = add nuw i32 %x, %y      ; no unsigned wrap: unsigned overflow makes it poison
%c = add nuw nsw i32 %x, %y  ; both guaranteed
```

- **`nsw`** corresponds to "signed overflow is UB" (C's default behaviour);
- **`nuw`** corresponds to "unsigned overflow is UB";
- both may appear together.

Which instructions support them:

| Instruction | `nsw` | `nuw` |
|---|---|---|
| `add`, `sub`, `mul` | ✓ | ✓ |
| `shl` | ✓ | ✓ |

**Note that `shl` supports `nsw`/`nuw`** — this is where `shl nsw i32 %0, 1` in the `p2` function of Chapter 3 comes from: it inherited the overflow semantics from `mul nsw`.

### `exact`

```llvm
%s = sdiv exact i32 %x, 4      ; guarantees exact division, otherwise poison
%u = udiv exact i32 %x, 4
%r = lshr exact i32 %x, 2
%a = ashr exact i32 %x, 2
```

`exact` means "this division/shift has no remainder (no bits are lost)". If there actually is a remainder, the result is poison.

**Why is it useful?** With `exact`, the optimizer knows that multiplying `sdiv exact %x, 4` back by 4 restores the original:

```llvm
%s = sdiv exact i32 %x, 4
%back = mul i32 %s, 4
; with exact, %back == %x, so it can be replaced
```

### Floating point flags

Floating point operations have a set of `fast-math` flags:

```llvm
%a = fadd fast double %x, %y
%b = fadd nnan ninf double %x, %y
```

| Flag | Meaning |
|---|---|
| `nnan` | assume there are no NaNs |
| `ninf` | assume there are no infinities |
| `nsz` | ignore the difference between positive and negative zero |
| `arcp` | allow replacing division with multiplication by the reciprocal |
| `contract` | allow fusion into an FMA |
| `afn` | allow approximate functions (such as a fast `sin`) |
| `reassoc` | allow reassociation (**breaks floating point associativity**) |
| `fast` | all of the above, the most aggressive |

**`fast` is extremely dangerous**: it lets the optimizer turn `(a+b)+c` into `a+(b+c)`, which is **not equivalent** in floating point. clang's `-ffast-math` generates these flags.

Measured:

```c
double sum3(double a, double b, double c) { return a + b + c; }
```

```bash
$ clang-18 -S -emit-llvm -O0 -ffast-math sum3.c -o -
```

Measured output (both additions carry `fast`):

```llvm
  %9  = fadd fast double %7, %8
  %11 = fadd fast double %9, %10
```

**`fast` authorizes the optimizer to reorder floating point operations.** For example it may rewrite `(a+b)+c` as `a+(b+c)` — which is **not equivalent** in floating point (the rounding differs). Unless you genuinely do not care about precision, do not use `-ffast-math`.

## 11.5 Memory access instructions

### `alloca`

```llvm
%p = alloca i32, align 4              ; one i32
%q = alloca i32, i32 %n, align 4      ; dynamic size (VLA)
%r = alloca %struct.Point, align 4    ; a struct
```

By default the allocation goes on the stack frame of the **entry block**. You can specify an address space:

```llvm
%s = alloca i32, addrspace(5)         ; allocate in address space 5
```

### `load` / `store`

```llvm
%v = load i32, ptr %p, align 4                    ; ordinary load
%w = load volatile i32, ptr %p, align 4           ; volatile (cannot be optimized away)
%x = load atomic i32, ptr %p seq_cst, align 4     ; atomic
store i32 %v, ptr %p, align 4                     ; ordinary store
store volatile i32 %v, ptr %p, align 4            ; volatile
store atomic i32 %v, ptr %p release, align 4      ; atomic
```

About `volatile`:

- **the semantics of `volatile` are "this access has side effects; it cannot be deleted, merged, or reordered"**;
- it does **not** guarantee atomicity;
- it corresponds to C's `volatile`.

About `atomic`:

- it guarantees atomicity and carries a memory ordering (`unordered`, `monotonic`, `acquire`, `release`, `acq_rel`, `seq_cst`);
- it corresponds to C11's `_Atomic`.

**Must `align` be written?** It may be omitted, in which case LLVM uses the type's ABI alignment as the default. But clang always writes it out explicitly.

### `getelementptr`

Already covered in detail in Chapter 6.

### Atomic read-modify-write

```llvm
%old = atomicrmw add ptr %p, i32 1 seq_cst       ; atomic add, returns the old value
%old2 = cmpxchg ptr %p, i32 %expected, i32 %new seq_cst seq_cst
```

The opcodes `atomicrmw` supports (measured on LLVM 18):

```
xchg  add  sub  and  nand  or  xor  max  min  umax  umin  uinc_wrap  udec_wrap
```

**Mind the naming trap**: `max`/`min` **are the signed versions**; the unsigned versions are called `umax`/`umin`. There is **no** `smax`/`smin` — this differs from the `slt`/`ult` naming habit of `icmp`; see [Appendix A.1.4](21-appendix-a-differences-from-common-claims.md#a14-atomicrmw-has-no-smaxsmin).

`cmpxchg` returns `{ old value, success flag }`.

These are used to implement lock-free data structures and correspond to C11's `atomic_fetch_add` and `atomic_compare_exchange`.

## 11.6 Conversion instructions

This is the biggest cliffhanger left by Part I. Conversion instructions come in four groups:

### Integer width

```llvm
%a = trunc i64 %x to i32      ; narrowing: discard the high bits
%b = zext i8 %c to i32        ; widening: fill the high bits with 0
%c = sext i32 %x to i64       ; widening: fill the high bits with the sign bit
```

`i1` → `i32` uses `zext` (Chapter 4), because an `i1` can only be 0 or 1, so filling with 0 is correct.

**`trunc` accepts no flags at all** (`nsw`, `nuw`, and `exact` are all rejected, with `expected type`) — see [Appendix A.1.3](21-appendix-a-differences-from-common-claims.md#a13-trunc-accepts-no-flags-at-all).

### `nneg` on `zext`

`zext` accepts an `nneg` flag:

```llvm
%6 = zext nneg i32 %5 to i33
```

`nneg` means "this source value is non-negative". With it, `zext` and `sext` produce the same result, so the optimizer can convert freely between the two. The optimization output for `sum_to` in Chapter 5 carries this flag — because there `%5 = add nsw i32 %0, -1`, and the code path already guarantees `%0 >= 1`, hence `%5 >= 0`.

**Back to the `i33` mystery** (an instance is in [Appendix B.6](22-appendix-b-optimization-primer.md#b6-watching-pass-by-pass-a-complete-experiment)):

```llvm
%4 = shl nuw i32 %0, 1
%5 = add nsw i32 %0, -1
%6 = zext nneg i32 %5 to i33
%7 = add nsw i32 %0, -2
%8 = zext i32 %7 to i33
%9 = mul i33 %6, %8
%10 = lshr i33 %9, 1
%11 = trunc i33 %10 to i32
```

This computes `sum_to(n) = n*(n+1)/2` with a 64-bit intermediate result, avoiding `i32` overflow. The `zext`s promote two `i32`s to `i33` (**note: 33 bits, not 32** — multiplying two 32-bit numbers needs at most 64 bits, but here the ability to shift has to be preserved, and 33 bits is a conservative choice that suffices); the multiplication is done in `i33` and then `trunc`'d back to `i32`.

**This code demonstrates the value of "arbitrary bit widths" perfectly**: in C you cannot declare a 33-bit integer, but IR can, so the optimizer can complete the computation in an intermediate type that is exactly wide enough.

### Pointers and integers

```llvm
%a = ptrtoint ptr %p to i64      ; pointer → integer
%b = inttoptr i64 %x to ptr      ; integer → pointer
```

They correspond to C's `(uintptr_t)p` and `(void *)x`.

### Floating point width

```llvm
%a = fptrunc double %x to float   ; narrowing
%b = fpext float %x to double     ; widening
```

### Floating point and integers

```llvm
%a = fptoui double %x to i32      ; floating point → unsigned integer (truncating)
%b = fptosi double %x to i32      ; floating point → signed integer
%c = uitofp i32 %x to double      ; unsigned integer → floating point
%d = sitofp i32 %x to double      ; signed integer → floating point
```

Measured:

```c
long sext_it(int x) { return x; }
int trunc_it(long x) { return (int)x; }
unsigned zext_it(unsigned char c) { return c; }
int sitofp_it(int x) { return (int)(double)x; }
double uitofp_it(unsigned u) { return (double)u; }
unsigned fptoui_it(double d) { return (unsigned)d; }
```

`-O2` output (excerpt):

```llvm
  %2 = sext i32 %0 to i64              ; sext_it
  %2 = trunc i64 %0 to i32             ; trunc_it
  %2 = zext i8 %0 to i32               ; zext_it
  %2 = uitofp i32 %0 to double         ; uitofp_it
  %2 = fptoui double %0 to i32         ; fptoui_it
```

**Note that `sitofp_it` generates no conversion instruction at all** — because `(int)(double)x` is the identity operation for `int`, and the optimizer removed it.

### `bitcast` and `addrspacecast`

```llvm
%a = bitcast i32 %x to float          ; bit reinterpretation (same width)
%b = addrspacecast ptr %p to ptr addrspace(1)
```

**In LLVM 18, `bitcast` is used far less than it used to be.** Because all pointers are `ptr`, all those old "pointer type conversion" `bitcast`s have disappeared. Today `bitcast` is mainly used for bit reinterpretation between integers and floating point values of the same width, and for vector type conversions.

Measured: the following C code produces **no instructions at all** under LLVM 18:

```c
int reinterp(int x) { return (unsigned)x; }
```

Under `-O0`:

```llvm
define dso_local i32 @reinterp(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  store i32 %0, ptr %2, align 4
  %3 = load i32, ptr %2, align 4
  ret i32 %3
}
```

Under `-O2`:

```llvm
define dso_local noundef i32 @reinterp(i32 noundef returned %0) local_unnamed_addr #0 {
  ret i32 %0
}
```

**Neither optimization level has a conversion instruction.** Because `int` and `unsigned` are both `i32` in IR, `(unsigned)x` is the identity operation. The `-O0` lines are debugging boilerplate (Chapter 2), and `-O2` simply returns the argument.

## 11.7 Aggregate and vector operations

```llvm
%a = extractvalue { i32, i32 } %pair, 1        ; extract a struct field
%b = insertvalue { i32, i32 } %pair, i32 5, 0  ; insert a struct field
%c = extractelement <4 x i32> %vec, i32 2      ; extract a vector element
%d = insertelement <4 x i32> %vec, i32 7, i32 0
%e = shufflevector <4 x i32> %v1, <4 x i32> %v2, <4 x i32> <i32 0, i32 4, i32 1, i32 5>
```

`extractvalue` / `insertvalue` work on **structs** (the index must be a constant).
`extractelement` / `insertelement` / `shufflevector` work on **vectors**.

**Note that `insertvalue` and `insertelement` produce a new value rather than modifying in place.** Because SSA values are immutable:

```llvm
%p0 = insertvalue { i32, i32 } undef, i32 1, 0
%p1 = insertvalue { i32, i32 } %p0, i32 2, 1    ; build a new one based on %p0
```

`shufflevector` is the core SIMD instruction; the `i32 0, i32 4` in the mask means "take element 0 of the first vector and element 0 of the second vector (index 4 = 4+0)".

## 11.8 `fneg`

```llvm
%r = fneg double %x
```

Floating point negation. **Integer negation uses `sub nsw i32 0, %x` (Chapter 3), but floating point has a dedicated `fneg`** — because whether the floating point `0.0 - x` gives `+0.0` or `-0.0` when `x` is `+0.0` is a delicate matter, and `fneg` has clearer semantics.

## 11.9 A quick reference table

| What you want to do | Instruction |
|---|---|
| Add, subtract, multiply | `add`, `sub`, `mul` (with `nsw`/`nuw`) |
| Divide | `sdiv`, `udiv` (may carry `exact`) |
| Remainder | `srem`, `urem` |
| Bitwise operations | `and`, `or`, `xor` |
| Shifts | `shl`, `lshr`, `ashr` |
| Negate | `xor x, -1` |
| Compare | `icmp`, `fcmp` |
| Conditional select (within a block) | `select` |
| Conditional select (across blocks) | `phi` |
| Widen an integer | `zext`, `sext` |
| Narrow an integer | `trunc` |
| Integer ↔ floating point | `sitofp`, `uitofp`, `fptosi`, `fptoui` |
| Widen/narrow a float | `fpext`, `fptrunc` |
| Pointer ↔ integer | `ptrtoint`, `inttoptr` |
| Take an address | `getelementptr` |
| Read/write memory | `load`, `store` |
| Stack allocation | `alloca` |
| Call | `call`, `invoke` |
| Jump | `br`, `switch`, `indirectbr` |
| Return | `ret` |
| Unreachable | `unreachable` |
| Freeze poison/undef | `freeze` |

## 11.10 Exercises

**Exercise 11.1** Hand-write a function that uses `nuw` instead of `nsw` and verify that `llvm-as-18` accepts it. Then think about when `nuw` and `nsw` have different optimization implications.

**Exercise 11.2** Generate a C program containing `volatile` reads and writes and atomic operations (using C11 `<stdatomic.h>`):

```c
#include <stdatomic.h>
int test(volatile int *p, _Atomic int *a) {
    int v = *p;
    atomic_fetch_add(a, 1);
    return v;
}
```

Find the `load volatile` and the `atomicrmw`.

**Exercise 11.3** Hand-write a function that uses `extractvalue` and `insertvalue` on a `{ i32, i32 }`. Validate it with `llvm-as-18`.

**Exercise 11.4** Use `shufflevector` to implement an operation that "interleaves two `<4 x i32>` values". What should the mask be?

**Exercise 11.5** Generate the `-O2` IR for `sum_to`, find those `zext ... to i33` instructions, explain what each step does, and then verify by hand that `sum_to(10) = 55`.

**Exercise 11.6 (thought question)** Why is `fneg` a separate instruction, while integer negation uses `sub 0, x`? Hint: think about `+0.0` and `-0.0` in IEEE 754.

## 11.11 Summary

- Six categories of instructions: terminators, unary, binary, memory access, conversions, other.
- **Every basic block must end with a terminator.**
- The flags `nsw`/`nuw`/`exact` are licences for the optimizer, derived from the source language's UB rules.
- The floating point `fast-math` flags (especially `fast`) break floating point semantics; use them with care.
- Conversion instructions come in four groups: integer width, pointer↔integer, floating point width, floating point↔integer.
- **LLVM supports arbitrary integer bit widths**, and the optimizer exploits this to create intermediate types such as `i33`.
- `volatile` guarantees "not optimized away" but not atomicity; `atomic` guarantees atomicity.
- `insertvalue`/`insertelement` produce **new values**, because SSA values are immutable.

Next chapter we cover attributes and metadata.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 10 Constants, Global Variables and Linkage](10-ch10-constants-and-globals.md) · [Next: Chapter 12 Attributes, Metadata and Intrinsics →](12-ch12-attributes-metadata-and-intrinsics.md)
