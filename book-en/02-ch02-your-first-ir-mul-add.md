# Chapter 2 Your First IR: The Three-Line Truth About `mul_add`

## 2.1 Starting from the smallest function

This is the first C function in the book, and the anchor for the whole book:

```c
int mul_add(int x, int y, int z) {
    return x * y + z;
}
```

Save the source as `mul_add.c` first. Now, open a terminal and run it yourself:

```bash
clang-18 -S -emit-llvm -O0 mul_add.c -o -
```

You will see (I have omitted the `; ModuleID`, `source_filename`, and `!llvm.ident` lines, which are irrelevant to teaching):

```llvm
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"

; Function Attrs: noinline nounwind optnone uwtable
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
  store i32 %0, ptr %4, align 4
  store i32 %1, ptr %5, align 4
  store i32 %2, ptr %6, align 4
  %7 = load i32, ptr %4, align 4
  %8 = load i32, ptr %5, align 4
  %9 = mul nsw i32 %7, %8
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
  ret i32 %11
}

attributes #0 = { noinline nounwind optnone uwtable "frame-pointer"="all" "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
```

## 2.2 First, let us be clear about the "three lines"

Many LLVM IR tutorials — including what this book's introduction first said — will tell you that `mul_add` becomes **three lines: `mul`, `add`, `ret`**.

**Under `-O0`, that does not hold.**

The IR above **has 12 instructions in the function body** (3 `alloca`, 3 `store`, 3 `load`, 1 `mul`, 1 `add`, 1 `ret`), not 3. If you follow an old tutorial, write the code, and then find that your output is completely different from the book's, it is easy to suspect that you did something wrong. You did not do anything wrong; that claim simply omitted a precondition.

The truth is this: **"three lines" describes the optimized IR**. Let me run it again with `-O2`:

```bash
clang-18 -S -emit-llvm -O2 mul_add.c -o -
```

```llvm
; Function Attrs: mustprogress nofree norecurse nosync nounwind willreturn memory(none) uwtable
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) local_unnamed_addr #0 {
  %4 = mul nsw i32 %1, %0
  %5 = add nsw i32 %4, %2
  ret i32 %5
}
```

Now it really is three lines (`mul`, `add`, `ret`). And note two interesting details:

1. The multiplication is `mul nsw i32 %1, %0` — **the operands are in the reverse order**. Multiplication is commutative, and clang casually put `%0` in second position (this is usually because x86's `imul` instruction has an encoding preference, but this step happens at the IR level).
2. The parameter names start at `%0`, `%1`, `%2`, while the optimized instruction numbering starts at `%4` — because `%0..%2` are already taken by the parameters, and the function-level counter continues after 3.

**So this chapter has two things to teach you**, and they are equally important:

- What the IR under `-O0` looks like, and why those `alloca`/`store`/`load` **are not junk**;
- What the optimized IR looks like, and how the `alloca`s disappear.

## 2.3 Taking apart the `-O0` version line by line

### The function header

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
```

From left to right:

| Fragment | Meaning |
|---|---|
| `define` | "This is a function **definition**" (it has a body). If there is only a declaration and no body, use `declare`. |
| `dso_local` | Linkage: this symbol can be resolved inside the current "dynamic shared object," without going through the GOT/PLT. Roughly, "visible within the module." |
| `i32` | The **return type**. C's `int` is exactly 32 bits on x86-64 Linux. |
| `@mul_add` | The function name. The `@` prefix indicates a **global identifier** (functions, global variables). Local variables use `%`. |
| `(i32 noundef %0, ...)` | The parameter list. Each parameter has the form "type + attribute + name." |
| `noundef` | A parameter attribute: the caller guarantees not to pass `undef`/`poison`. This is a product of C semantics — passing an uninitialized value in C is UB. |
| `%0`, `%1`, `%2` | Parameter names. Under `-O0`, clang does not preserve the original parameter names. |
| `#0` | Refers to the attribute group `attributes #0 = {...}` below. |

About the numbering of `%0`, there is a rule you must know: **parameters take the numbers starting from 0 first, and instructions are numbered after them**.

The three parameters take `%0`, `%1`, `%2`, so the first instruction ought to be called `%3` — but it is actually `%4`. This "skipped number" is not a typo but part of LLVM's implicit numbering rules. Let us test it: first look at a function with only one parameter:

```c
int one(int a) { return a + 1; }
```

```llvm
define dso_local i32 @one(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  ...
```

One parameter takes only `%0`, yet the first instruction is `%2`, skipping `%1`. Now look at one with two parameters:

```c
int two(int a, int b) { return a + b; }
```

```llvm
define dso_local i32 @two(i32 noundef %0, i32 noundef %1) #0 {
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  ...
```

The two parameters take `%0`, `%1`, and the first instruction is `%3` — this time there is **no** skipped number.

The rule is hidden here: **basic block labels and "instructions that produce a value" share the same numbering counter, while instructions that do not produce a value do not consume a number.**

In `two`, the two parameters take `%0`, `%1`, and the anonymous entry basic block takes `%2`, so the first `alloca` is `%3`.

In `one`, the parameter takes `%0`, the entry block takes `%1`, so the first `alloca` is `%2` — that is the truth behind the "skipped number."

`mul_add` is the same: the three parameters take `%0`–`%2`, the entry block takes `%3`, and the first `alloca` is `%4`.

Now look at a function with a branch; the evidence is even more direct:

```c
int withbranch(int a) {
    if (a > 0) return 1;
    return 2;
}
```

```llvm
define dso_local i32 @withbranch(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 %0, ptr %3, align 4
  %4 = load i32, ptr %3, align 4
  %5 = icmp sgt i32 %4, 0
  br i1 %5, label %6, label %7

6:                                                ; preds = %1
  store i32 1, ptr %2, align 4
  br label %8
  ...
```

`label %6`, `%7`, `%8` are all **basic blocks**, not values. And the comment `; preds = %1` reveals that the name of the entry block is `%1`.

You do not need to memorize these details. What this chapter really wants you to remember is the practical conclusion: **do not hand-write numbers; let LLVM number things itself; if your compiler must number them itself, then give every value a name (`%t1`, `%a`) and avoid the whole implicit counting rule.** Chapter 8 revisits this rule, and in Chapter 17, when we write the compiler, we will see how it really bites.

### The three `alloca`s

```llvm
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
```

`alloca` allocates a piece of space **on the current function's stack frame** and returns a pointer to it.

- `alloca i32` — allocate a space the size of one `i32`.
- `align 4` — this memory is aligned to 4 bytes.
- The return type is `ptr` (LLVM 18's unified pointer type).

The three `alloca`s correspond to the three parameters `x`, `y`, `z`. **Why copy the parameters onto the stack again?** The parameters are already in registers.

The answer is **debugging experience**. Under `-O0`, the compiler promises: when you `print x` in gdb, you will always see the correct value. If `x` stayed in a register and that register were reused by later code, the debugger would not be able to see it. Storing the parameter into memory guarantees that it has a stable address for the entire lifetime of the function.

This is why the IR under `-O0` is full of `alloca`/`store`/`load`: **it is serving the debugger, not the CPU**.

### The three `store`s

```llvm
  store i32 %0, ptr %4, align 4
  store i32 %1, ptr %5, align 4
  store i32 %2, ptr %6, align 4
```

These write the parameter values into the slots just allocated. The syntax of `store` is:

```
store <type> <value>, ptr <target address>, align <alignment>
```

Note an LLVM 18 characteristic here: the destination address is written `ptr`, **not** `i32*`. In older LLVM (≤14) you would see `store i32 %0, i32* %4, align 4`. LLVM 18 uses opaque pointers, so all pointers are `ptr`, and the type information is provided by the first operand of `store` (`i32`).

### The two `load`s and the `mul`

```llvm
  %7 = load i32, ptr %4, align 4
  %8 = load i32, ptr %5, align 4
  %9 = mul nsw i32 %7, %8
```

`load` reads an `i32` out of memory. `mul` multiplies them.

**What is `nsw`?** It is `No Signed Wrap`. This keyword means: **if this multiplication overflows as a signed value, the result is `poison`, not the wrapped-around value**.

This is a direct mapping of C semantics. The C standard specifies that signed integer overflow is **undefined behaviour**. Since the programmer guarantees there will be no overflow, the compiler can boldly assume there is none and write that assumption into the IR. If it does overflow in practice, the program's behaviour is undefined — the compiler bears no responsibility whatsoever.

`nsw` is the precondition that makes many later aggressive optimizations valid. Chapter 11 expands on this in detail.

### `add` and `ret`

```llvm
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
  ret i32 %11
```

`ret i32 %11` returns the value and ends the function.

## 2.4 An observation: the SSA form

Now focus your attention on this fact:

```llvm
  %7 = load i32, ptr %4, align 4
  %8 = load i32, ptr %5, align 4
  %9 = mul nsw i32 %7, %8
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
```

**Every `%n` is assigned exactly once.** In IR this is a hard rule, called the **SSA (Static Single Assignment) form**.

In C you can write this:

```c
int x = 1;
x = x + 1;   // the same variable is assigned twice
x = x * 2;
```

In IR this is **illegal**. You cannot write `%7 = ...` and then assign something else to it. Each assignment produces a **brand-new name**.

So the question arises: how are mutable variables from C represented in IR?

**The answer is `alloca` + `store` + `load`.** Memory is mutable; SSA values are not. The variable `x` lives in the memory at `%4`:

```llvm
  %4 = alloca i32          ; allocate space for x
  store i32 1, ptr %4      ; x = 1
  %7 = load i32, ptr %4    ; read x
  %8 = add i32 %7, 1       ; x + 1
  store i32 %8, ptr %4     ; x = x + 1
```

**This is the second reason memory operations are everywhere under `-O0`** — it is the least troublesome way to translate mutable C variables into the immutable SSA form.

And in Chapter 20 we will see that LLVM's `mem2reg` pass can **turn these memory operations back into SSA values**, automatically inserting `phi` nodes where needed. In other words, clang `-O0` takes the route of "store to memory first, optimize it away later."

## 2.5 From `-O0` to `-O2`: how the `alloca`s disappear

The above has already answered "why the IR under `-O0` is so bloated." The natural next question is: **where do they all go after optimization?**

The short answer: a pass called `mem2reg` **promotes** "stack slots whose address is never taken" into SSA values, automatically inserting `phi` where needed. In our example, 12 instructions become 3.

The full experiment (including the commands, the output, and why running `opt` directly may do nothing at all) is in [Appendix B.1](22-appendix-b-optimization-primer.md#b1-why-alloca-disappears-mem2reg) and [Appendix B.2](22-appendix-b-optimization-primer.md#b2-why-running-opt-does-nothing-optnone).

## 2.6 The complete comparison table

| C source | IR (`-O0`) | IR (`-O2`) |
|---|---|---|
| Function signature `int mul_add(int,int,int)` | `define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0` | `define dso_local i32 @mul_add(...) local_unnamed_addr #0` |
| Storage of parameter `x` | `%4 = alloca i32, align 4` + `store i32 %0, ptr %4, align 4` | Gone (parameters are directly in registers) |
| `x * y` | `%7 = load ...; %8 = load ...; %9 = mul nsw i32 %7, %8` | `%4 = mul nsw i32 %1, %0` |
| `... + z` | `%10 = load ...; %11 = add nsw i32 %9, %10` | `%5 = add nsw i32 %4, %2` |
| `return` | `ret i32 %11` | `ret i32 %5` |
| Instruction count | 12 | 3 |

## 2.7 Exercises

**Exercise 2.1** Change `int` to `long` and regenerate the IR. What do you expect `i32` to become? Verify it.

**Exercise 2.2** Change the function to `float mul_add(float x, float y, float z)`. What does `mul` become? (Hint: floating point has its own instructions.)

**Exercise 2.3** Add an "unused" variable inside the function:

```c
int mul_add(int x, int y, int z) {
    int unused = 99;
    return x * y + z;
}
```

How do `-O0` and `-O2` each handle `unused`?

**Exercise 2.4** Try `clang-18 -S -emit-llvm -O1 mul_add.c -o -` and compare whether the output of `-O1` and `-O2` is the same.

**Exercise 2.5 (important)** Use `opt-18 -passes=mem2reg` on the `-O0` IR of some C file you wrote yourself. If nothing changes, think about why.

## 2.8 Summary

- The body of `mul_add` is **12 instructions** under `-O0`, and only **3** under `-O2`. Tutorials that claim "always three lines" omitted the precondition.
- `alloca`/`store`/`load` exist for two reasons: **serving the debugger**, and **translating mutable C variables into the immutable SSA form**.
- IR is in SSA form: every `%name` is assigned only once. Mutable state must go through memory.
- `nsw` encodes C's stipulation that "signed overflow is UB."
- LLVM 18 uses `ptr`, not `i32*`.
- `optnone` silently disables all optimization passes — this is an explicit requirement of `-O0`.

In the next chapter, we take a look at the whole landscape of arithmetic, logic, and shifts.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 1 Why LLVM IR Is Worth Learning](01-ch01-why-learn-llvm-ir.md) · [Next: Chapter 3 Arithmetic, Logic and Shifts →](03-ch03-arithmetic-logic-and-shifts.md)
