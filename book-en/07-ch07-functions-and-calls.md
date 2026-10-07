# Chapter 7 Functions, Calling Conventions and Linkage

## 7.1 Definitions and Declarations

Functions have two forms in IR:

```llvm
define i32 @defined_here(i32 %x) {    ; has a body -- definition
  ret i32 %x
}

declare i32 @defined_elsewhere(i32)   ; no body -- declaration
```

| | `define` | `declare` |
|---|---|---|
| Has a body | Yes | No |
| Parameter names | Needed (they are used in the body) | Usually omitted |
| Equivalent to C's | function definition | `extern` declaration / a prototype from `#include` |

Let us measure. First a call to an external function:

```c
int add(int, int);                      /* declaration */
int call_add(int a, int b) { return add(a, b); }
```

`-O0`:

```llvm
define dso_local i32 @call_add(i32 noundef %0, i32 noundef %1) #0 {
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  store i32 %0, ptr %3, align 4
  store i32 %1, ptr %4, align 4
  %5 = load i32, ptr %3, align 4
  %6 = load i32, ptr %4, align 4
  %7 = call i32 @add(i32 noundef %5, i32 noundef %6)
  ret i32 %7
}

declare i32 @add(i32 noundef, i32 noundef) #1
```

Two things worth noting:

1. **`call i32 @add(i32 noundef %5, i32 noundef %6)`** — note that the arguments also carry `noundef`. This is a parameter attribute meaning "this argument will not be `undef`".
2. **The `declare` statement appears after the function body.** The relative positions of `declare` and `define` in an IR file are free, but by convention clang puts undefined symbols later.

**The parameters of a `declare` have no names** (`i32 noundef` rather than `i32 noundef %x`), because there is no body and no need to reference the parameters.

## 7.2 Recursion and Mutual Recursion

Recursion is nothing special in IR — a function calling itself is an ordinary `call`:

```c
int fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); }
```

`-O0`:

```llvm
define dso_local i32 @fact(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  store i32 %0, ptr %2, align 4
  %3 = load i32, ptr %2, align 4
  %4 = icmp sle i32 %3, 1
  br i1 %4, label %5, label %6

5:                                                ; preds = %1
  br label %12

6:                                                ; preds = %1
  %7 = load i32, ptr %2, align 4
  %8 = load i32, ptr %2, align 4
  %9 = sub nsw i32 %8, 1
  %10 = call i32 @fact(i32 noundef %9)
  %11 = mul nsw i32 %7, %10
  br label %12

12:                                               ; preds = %6, %5
  %13 = phi i32 [ 1, %5 ], [ %11, %6 ]
  ret i32 %13
}
```

**There is a `phi` here!** And it is the best teaching sample in this chapter:

```llvm
12:                                               ; preds = %6, %5
  %13 = phi i32 [ 1, %5 ], [ %11, %6 ]
```

Read it as: coming from `%5` (the base case), the result is `1`; coming from `%6` (the recursive step), the result is `%11` (`n * fact(n-1)`).

Note that block `%5` contains **no `load`** — it uses the constant `1` directly. This is why clang chose `phi` here rather than "store the return value into a memory slot": the result of a ternary operator is a **pure expression**, and clang is willing to generate SSA form for it even at `-O0`.

**Mutual recursion** is no different:

```c
static int helper(int x) { return x * 3; }
int use_helper(int x) { return helper(x); }
```

```llvm
define dso_local i32 @use_helper(i32 noundef %0) #0 {
  ...
  %4 = call i32 @helper(i32 noundef %3)
  ret i32 %4
}

define internal i32 @helper(i32 noundef %0) #0 {
  ...
  %4 = mul nsw i32 %3, 3
  ret i32 %4
}
```

Note `define internal i32 @helper` — `static` becomes `internal`, just as with global variables.

## 7.3 Indirect Calls: Function Pointers

```c
int apply(int (*f)(int,int), int a, int b) { return f(a, b); }
```

```llvm
define dso_local i32 @apply(ptr noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  ...
  %7 = load ptr, ptr %4, align 8
  %8 = load i32, ptr %5, align 4
  %9 = load i32, ptr %6, align 4
  %10 = call i32 %7(i32 noundef %8, i32 noundef %9)
  ret i32 %10
}
```

**`call i32 %7(...)`** — the callee is a **value** (`%7`), not a function name. This is an indirect call.

In LLVM 18 a function pointer is just an ordinary `ptr` (because of opaque pointers). In older LLVM (≤14) you would see `call i32 %7(...)` where the type of `%7` is `i32 (i32, i32)*` — a **function pointer type**. Opaque pointers unified all of this into `ptr`.

**Where did the type information go?** It moved into the `call` instruction. `call i32 %7(i32 noundef %8, i32 noundef %9)` states the return type and the parameter types completely. This is the design point of opaque pointers: **type information is no longer "part of the pointer" but "part of the instruction that uses it".**

## 7.4 Variadic Functions

```c
#include <stdarg.h>
int sum_n(int n, ...) {
    va_list ap;
    va_start(ap, n);
    int s = 0;
    for (int i = 0; i < n; i++) s += va_arg(ap, int);
    va_end(ap);
    return s;
}
```

The beginning of `-O0`:

```llvm
%struct.__va_list_tag = type { i32, i32, ptr, ptr }

define dso_local i32 @sum_n(i32 noundef %0, ...) #0 {
  %2 = alloca i32, align 4
  %3 = alloca [1 x %struct.__va_list_tag], align 16
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  store i32 %0, ptr %2, align 4
  %6 = getelementptr inbounds [1 x %struct.__va_list_tag], ptr %3, i64 0, i64 0
  call void @llvm.va_start(ptr %6)
  ...
```

The points:

1. **`define dso_local i32 @sum_n(i32 noundef %0, ...)`** — the `...` at the end of the parameter list is the variadic marker. This is the only way IR expresses "the number of arguments is not fixed".
2. **`va_list` is a concrete type**, `%struct.__va_list_tag`, whose details are determined by the target platform. The x86-64 SysV `va_list` contains the register save area offset, the overflow area pointer and so on, hence `{ i32, i32, ptr, ptr }`.
3. **`llvm.va_start` / `llvm.va_arg` / `llvm.va_end` are intrinsics**, not ordinary library functions. They are called with an ordinary `call`, but their names begin with `llvm.`.

**Variadic functions are a typical example of "target dependent".** The IR above is meaningful only on x86-64 SysV. On another target platform the definition of `%struct.__va_list_tag` is completely different. This is one of the few places where IR is not entirely target independent.

When calling a variadic function, the parameter types must be declared in the `call`:

```llvm
%r = call i32 (ptr, ...) @printf(ptr @fmt, i32 %v)
```

Note `call i32 (ptr, ...) @printf(...)` — the function **type** is written explicitly in front of the callee, because `@printf` is variadic and the complete signature cannot be inferred from the arguments alone.

## 7.5 Inlining and Function Attributes

```c
__attribute__((noinline)) int noinline_f(int x) { return x; }
__attribute__((always_inline)) static inline int always_f(int x) { return x + 1; }
__attribute__((noreturn)) void die(void) { __builtin_trap(); }
int use_inline(int x) { return always_f(x); }
```

`-O2`:

```llvm
; Function Attrs: mustprogress nofree noinline norecurse nosync nounwind willreturn memory(none) uwtable
define dso_local noundef i32 @noinline_f(i32 noundef returned %0) local_unnamed_addr #0 {
  ret i32 %0
}

; Function Attrs: noreturn nounwind memory(inaccessiblemem: write) uwtable
define dso_local void @die() local_unnamed_addr #1 {
  tail call void @llvm.trap()
  unreachable
}

; Function Attrs: cold noreturn nounwind memory(inaccessiblemem: write)
declare void @llvm.trap() #2

; Function Attrs: mustprogress nofree norecurse nosync nounwind willreturn memory(none) uwtable
define dso_local i32 @use_inline(i32 noundef %0) local_unnamed_addr #3 {
  %2 = add nsw i32 %0, 1
  ret i32 %2
}
```

Four observations:

1. **`noinline_f` keeps the `noinline` attribute**, and `returned %0` appears — this is a parameter attribute meaning "the return value is `%0`", which lets the caller skip a copy.

2. **`always_f` has disappeared completely!** There is no `define` and no `declare`. Its body was **inlined** into `use_inline`: `%2 = add nsw i32 %0, 1`. `always_inline` took effect, and because the function is `static` (`internal`) with no other users, LLVM deleted it entirely.

3. **`die` ends with `unreachable`** instead of `ret void`. Because it is `noreturn`, it never returns:

   ```llvm
   tail call void @llvm.trap()
   unreachable
   ```

   `unreachable` is a **terminator**, and it tells the optimizer: "execution cannot reach here". If it somehow does, the behaviour is undefined — which gives the optimizer enormous freedom (it can delete code after `unreachable` as dead code).

4. **`tail call void @llvm.trap()`** — the `tail` marker says this is a tail call and can be optimized into a jump rather than a call. `llvm.trap()` triggers a trap instruction (`ud2` on x86), so it really does not return.

### Attribute Groups

Note the references `#0`, `#1`, `#2`, `#3`; they point at attribute groups at the end of the file:

```llvm
attributes #0 = { mustprogress nofree noinline norecurse nosync nounwind willreturn memory(none) uwtable "min-legal-vector-width"="0" ... }
```

Attribute groups exist to **deduplicate**: when several functions share the same set of attributes, it only needs to be written once. Chapter 12 explains the meaning of these attributes in detail.

## 7.6 Calling Conventions

Both `define` and `call` can carry a **calling convention**:

```llvm
define fastcc i32 @fast_fn(i32 %x) {
  ret i32 %x
}

define i32 @caller(i32 %x) {
  %r = call fastcc i32 @fast_fn(i32 %x)
  ret i32 %r
}
```

The common calling conventions:

| Keyword | Meaning |
|---|---|
| (omitted) | The C calling convention (`ccc`), the target platform default |
| `fastcc` | Put arguments in registers as much as possible; used for internal functions |
| `coldcc` | For paths that are rarely executed |
| `cc 10` | The GHC convention; `cc 11` is HiPE; the specific numbers are platform specific |

`fastcc` is the convention LLVM uses internally: it does not follow the platform ABI, so argument passing can be more flexible. **The price is that it cannot be called by external code.** So clang only uses it for `internal` functions.

A measurement (note that `-fno-inline` must be added, otherwise this function gets inlined and we cannot see it):

```c
static int helper(int x) { return x * 2; }
int pub(int x) { return helper(x) + 1; }
```

```bash
clang-18 -S -emit-llvm -O2 -fno-inline fastc.c -o -
```

```llvm
define dso_local i32 @pub(i32 noundef %0) local_unnamed_addr #0 {
  ...
}

define internal fastcc i32 @helper(i32 noundef %0) unnamed_addr #0 {
  ...
}
```

`@helper` is `internal` (C's `static`), so clang confidently gives it `fastcc`. `@pub` is externally visible and must follow the platform ABI, so it uses the default calling convention.

At `-O0` you will hardly ever see `fastcc`, because `-O0` must preserve ABI compatibility for debugging. This is **another reason `-O0` output is "verbose"**: it must strictly follow the platform calling convention.

(By the way, note that `@helper` uses `unnamed_addr` while `@pub` uses `local_unnamed_addr`. The former means "the address of this function does not matter", the latter means "the address does not matter within the module but may matter outside it". Subtleties like this are entirely the result of optimizer inference; there is no need to memorize them.)

## 7.7 Linkage at a Glance

The linkage of a function determines its visibility at link time:

| IR | C counterpart | Meaning |
|---|---|---|
| (default) | an ordinary function | Externally visible, defined in this module |
| `internal` | `static` | Visible only within the module |
| `private` | no direct counterpart | Visible only within the module, and absent from the symbol table |
| `external` | an `extern` declaration | Defined elsewhere |
| `linkonce_odr` | templates/inline functions | May be defined repeatedly; the linker keeps one copy |
| `weak` | `__attribute__((weak))` | Can be overridden by a stronger definition |
| `available_externally` | — | Used only for inlining, no code generated |

A `dso_local` is **not** a linkage; it is "symbol binding" information: it says this symbol can be resolved inside the current shared library without going through the GOT.

## 7.8 Exercises

**Exercise 7.1** Generate the `-O0` IR for `int fact(int n)`, find the `phi`, and explain every one of its operands word by word. Then run `mem2reg` and see whether the `phi` changes.

**Exercise 7.2** Hand-write an `.ll` file defining `@square(i32) -> i32`, then define `@main()` that calls it and returns `square(7)`. Verify it with `llvm-as-18`, execute it with `lli-18`, and confirm the exit code is 49.

**Exercise 7.3** Generate the IR for a C program containing a `printf` call. Find `call i32 (ptr, ...) @printf(...)` and explain why the type is written twice.

**Exercise 7.4** Compile a function marked `__attribute__((noreturn))` and confirm it ends with `unreachable`. Then hand-write a version ending with `ret void` and think about what the semantic difference is.

**Exercise 7.5** Turn the IR of `apply` (function pointer) into a hand-written version, verify it with `llvm-as-18`, and use a C driver to call a real function pointer.

**Exercise 7.6 (thinking question)** In LLVM 14 the type of `%7` in `apply` is `i32 (i32, i32)*`. In LLVM 18 it is `ptr`. The type information moved from one place to another — say where it moved and why this design is better.

## 7.9 Summary

- `define` is a definition, `declare` is a declaration.
- Recursion and mutual recursion are nothing special in IR; they are ordinary `call`s.
- An indirect call is written `call <ret> %ptr(args...)`; in LLVM 18 a function pointer is `ptr` and the type information lives on the `call` instruction.
- Variadic functions use `...` and are implemented through intrinsics such as `llvm.va_start`; they are target dependent.
- `unreachable` is a terminator, used for `noreturn` functions.
- The attribute groups `#0`, `#1` are used for deduplication.
- Calling conventions (`fastcc` and friends) let LLVM use non-ABI argument passing, but they are only safe for internal functions.

**This is the end of Part I.** You should now be able to: look at a C function and roughly picture the shape of its IR; look at a piece of IR and say clearly what it is doing.

In the next part we fill in the syntax systematically. Each chapter first refers back to a concrete example from Part I, and then goes from "why" to "what".

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 6 Memory, Pointers and `getelementptr`](06-ch06-memory-and-getelementptr.md) · [Next: Chapter 8 Modules, Identifiers and Naming Rules →](08-ch08-identifiers-and-naming.md)
