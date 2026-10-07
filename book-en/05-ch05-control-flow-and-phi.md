# Chapter 5 Control Flow: `br`, Basic Blocks and `phi`

This is the most important chapter in the book. `phi` is the most distinctive, least intuitive, and most SSA-revealing construct in LLVM IR. For the previous four chapters you have been asking "why is `-O0` so verbose"; this chapter shows you what that verbosity buys.

## 5.1 Starting from a Ternary Operator

```c
int pick(int c, int a, int b) { return c ? a : b; }
```

`clang-18 -S -emit-llvm -O0`:

```llvm
define dso_local i32 @pick(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
  store i32 %0, ptr %4, align 4
  store i32 %1, ptr %5, align 4
  store i32 %2, ptr %6, align 4
  %7 = load i32, ptr %4, align 4
  %8 = icmp ne i32 %7, 0
  br i1 %8, label %9, label %11
9:                                                ; preds = %3
  %10 = load i32, ptr %5, align 4
  br label %13
11:                                               ; preds = %3
  %12 = load i32, ptr %6, align 4
  br label %13
13:                                               ; preds = %11, %9
  %14 = phi i32 [ %10, %9 ], [ %12, %11 ]
  ret i32 %14
}
```

Setting aside the boilerplate of the first 8 lines (`alloca`/`store`, already explained in Chapter 2), the structure is very clear:

```
        entry block (%4 to %8, then br)
         /                    \
   br i1 %8                  
      /                        \
   block %9 (then)          block %11 (else)
   %10 = load a             %12 = load b
   br label %13             br label %13
      \                        /
       \                      /
        block %13 (merge)
        %14 = phi i32 [ %10, %9 ], [ %12, %11 ]
        ret i32 %14
```

- **`br i1 %8, label %9, label %11`** — a conditional branch. The condition is `i1` (the "tyranny" of Chapter 4), and the two targets are the true branch and the false branch.
- **`br label %13`** — an unconditional branch.
- **Basic block** — each `label:` starts a new block. A basic block is "a sequence of instructions with a single entry and a single exit".
- **`%14 = phi i32 [ %10, %9 ], [ %12, %11 ]`** — this is the first time we meet `phi`.

## 5.2 What `phi` Is Actually Saying

First the syntax:

```llvm
%14 = phi i32 [ %10, %9 ], [ %12, %11 ]
```

Read it from left to right:

- `%14` — the value this `phi` produces.
- `phi i32` — it produces an `i32`.
- `[ %10, %9 ]` — "if I came here from basic block **`%9`**, then my value is **`%10`**".
- `[ %12, %11 ]` — "if I came here from basic block **`%11`**, then my value is **`%12`**".

**Every `[value, predecessor block]` pair reads as "coming from that block means taking this value".**

Describing `%14` in block `%13` in plain language:

> I am the merge point. Whoever jumps to me, I ask where they came from.
> - Coming from `%9` (the then branch), I give you `%10`, which is the value of `a`.
> - Coming from `%11` (the else branch), I give you `%12`, which is the value of `b`.

**Why is it needed?** Go back to the iron law of SSA from Chapter 2: **each `%name` can be assigned only once.**

In C, the result of `c ? a : b` is a "variable" that is given different values on the two paths. But in SSA you **cannot** write:

```llvm
9:
  %result = ...        ; illegal: %result on this path
  br label %13
11:
  %result = ...        ; illegal: assigned a second time!
  br label %13
13:
  ret i32 %result
```

because `%result` is defined twice. So which one does `%result` in `%13` refer to? SSA does not allow that ambiguity.

`phi` is the **only legal** solution: put one instruction at the merge point that picks the right value according to "which path you came from". **It is not a run-time instruction but a compile-time "wiring" declaration.**

### An intuition you must build: `phi` "does not execute" at run time

This is the most confusing point. There is no "phi instruction" on a CPU. By the time block `%13` starts executing, the value of `%14` is **already determined** — it equals the value computed on the path just taken.

You can think of it this way: **`phi` is a "selection description" written at the merge point, not an operation to be executed.** Modern compiler backends turn it into register allocation or `cmov`, producing no extra cost.

### The predecessor blocks must match

The predecessor blocks listed in a `phi` must be **exactly** the real predecessor set of that basic block. The verifier checks this strictly:

```llvm
define i32 @f(i32 %a, i32 %b) {
entry:
  %c = icmp sgt i32 %a, %b
  br i1 %c, label %t, label %f
t:
  br label %m
f:
  br label %m
m:
  %r = phi i32 [ %a, %t ], [ %b, %entry ]    ; ← wrong: %entry is not a predecessor of %m
  ret i32 %r
}
```

```bash
$ llvm-as-18 bad_phi.ll -o /dev/null
llvm-as-18: assembly parsed, but does not verify as correct!
PHI node entries do not match predecessors!
  %r = phi i32 [ %a, %t ], [ %b, %entry ]
label %entry
label %t
```

The verifier lists the predecessors it thinks "should be" there (`%entry` and `%t`) and points out that the `%entry` you wrote is not among them. **We will make this mistake ourselves in Chapter 18**, and then you will see what it looks like and why it is so hard to track down.

## 5.3 Full Side-by-Side Comparison: `if` / `else`

```c
int abs_v(int x) {
    if (x < 0)
        return -x;
    return x;
}
```

`-O0`:

```llvm
define dso_local i32 @abs_v(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 %0, ptr %3, align 4
  %4 = load i32, ptr %3, align 4
  %5 = icmp slt i32 %4, 0
  br i1 %5, label %6, label %9

6:                                                ; preds = %1
  %7 = load i32, ptr %3, align 4
  %8 = sub nsw i32 0, %7
  store i32 %8, ptr %2, align 4
  br label %11

9:                                                ; preds = %1
  %10 = load i32, ptr %3, align 4
  store i32 %10, ptr %2, align 4
  br label %11

11:                                               ; preds = %9, %6
  %12 = load i32, ptr %2, align 4
  ret i32 %12
}
```

**Note that there is no `phi` here.** Why? Because clang used a trick: it allocated a slot `%2` for the **return value** (note that `%2` is the first `alloca`, earlier than the slot `%3` for the parameter `x`). Each branch `store`s into `%2`, and then `%11` does a single `load`.

**Memory plays the role of `phi`.** This is what "mutable variables live in memory" from Chapter 2 looks like in terms of control flow: once a value lives in memory, passing it across branches needs no `phi`, only one `store` and one `load`.

So you should now be able to appreciate this rule of thumb:

> **In `-O0` IR, `phi` appears where the optimizer has already done register promotion, or where clang thinks it is worth generating SSA directly (such as a ternary operator).** The vast majority of C variables are memory slots at `-O0`, so they need no `phi`.

## 5.4 Full Side-by-Side Comparison: Loops

Loops are the most important use case for `phi`. Look:

```c
int sum_to(int n) {
    int s = 0;
    for (int i = 1; i <= n; i++)
        s += i;
    return s;
}
```

`-O0`:

```llvm
define dso_local i32 @sum_to(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  store i32 %0, ptr %2, align 4
  store i32 0, ptr %3, align 4
  store i32 1, ptr %4, align 4
  br label %5

5:                                                ; preds = %13, %1
  %6 = load i32, ptr %4, align 4
  %7 = load i32, ptr %2, align 4
  %8 = icmp sle i32 %6, %7
  br i1 %8, label %9, label %16

9:                                                ; preds = %5
  %10 = load i32, ptr %4, align 4
  %11 = load i32, ptr %3, align 4
  %12 = add nsw i32 %11, %10
  store i32 %12, ptr %3, align 4
  br label %13

13:                                               ; preds = %9
  %14 = load i32, ptr %4, align 4
  %15 = add nsw i32 %14, 1
  store i32 %15, ptr %4, align 4
  br label %5, !llvm.loop !6

16:                                               ; preds = %5
  %17 = load i32, ptr %3, align 4
  ret i32 %17
}
```

The structure:

```
      Entry (store initializers, br -> %5)
              |
              v
       %5 (condition block) ←──────────┐
       load i, load n          │
       icmp, br ──┐            │
        /         \            │
       v           v           │
   %9 (loop body)   %16 (exit) │
   accumulate       return s   │
   br -> %13                   │
       |                       │
       v                       │
   %13 (increment block)       │
   i = i + 1                   │
   br -> %5 ────────────────────┘
```

A few things to note:

1. **`%5` has two predecessors**: the entry block and `%13`.
2. **`br label %5, !llvm.loop !6`** — that `!llvm.loop` is loop metadata, telling the optimizer "this is a loop". This is something `-O0` generates too (Chapter 12 covers it).
3. **Still no `phi`** — because `i` and `s` both live in memory.

So when does `phi` appear? **When the optimizer promotes memory to registers.**

## 5.5 Where `phi` Comes From

The loop above has **no `phi`** — because the variables all live in memory (Section 5.4).

So when will you see `phi` in a loop? **When the optimizer promotes memory to registers.** That process (how `mem2reg` creates `phi`s for loop variables) demonstrates the whole reason `phi` exists, and it lives in [Appendix B.3](22-appendix-b-optimization-primer.md#b3-witnessing-the-birth-of-phi).

A one-sentence preview: a variable that is repeatedly modified inside a loop must, in SSA, be "renamed" into several values on several paths, and the merge point needs `phi` to decide which one to take. **In Chapter 20 you will see that our own generated loops produce a completely isomorphic structure after `mem2reg`.**

## 5.6 A Hands-on Measurement of `phi`

Theory says `phi` "does not execute" at run time. Let us prove it, and at the same time verify that the output of `mem2reg` is correct:

```bash
cat > loop_phi.ll <<'EOF'
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
EOF

cat > main.c <<'EOF'
#include <stdio.h>
int loop_phi(int);
int main(void) {
    printf("loop_phi(10) = %d\n", loop_phi(10));
    printf("loop_phi(100) = %d\n", loop_phi(100));
    return 0;
}
EOF

llvm-as-18 loop_phi.ll -o loop_phi.bc
clang-18 -w main.c loop_phi.bc -o test
./test
```

The actual output:

```
loop_phi(10) = 45
loop_phi(100) = 4950
```

(0+1+...+9 = 45; 0+...+99 = 4950.) The hand-written `phi` works correctly.

## 5.7 The Other Option: `select`

If both branches merely **evaluate** something and have no side effects, then you do not necessarily need a branch plus `phi`. IR provides `select`:

```llvm
%r = select i1 %cond, i32 %a, i32 %b
```

The semantics are: if `cond` is true take `%a`, otherwise take `%b`. **It does not evaluate control flow; the values on both paths must be computed first.**

Compare the output of the same C code at `-O0` and `-O2`:

```c
int pick(int c, int a, int b) { return c ? a : b; }
```

`-O0` (seen earlier): `br` + `phi`, 15 instructions in the function body.

`-O2`:

```llvm
define dso_local noundef i32 @pick(i32 noundef %0, i32 noundef %1, i32 noundef %2) local_unnamed_addr #0 {
  %4 = icmp eq i32 %0, 0
  %5 = select i1 %4, i32 %2, i32 %1
  ret i32 %5
}
```

**Three instructions**, the branch and the `phi` are gone, replaced by `select`.

When can `select` be used? When "evaluate both paths" and "evaluate only one" **give the same result**. For `c ? a : b`, `a` and `b` are just two already-computed values, and "evaluating" both of them is free, so `select` is better.

When **can't** it be used? When one of the paths has a side effect or may crash:

```c
int safe_div(int *p, int d) { return p ? *p / d : 0; }
```

Here, if `p` is `NULL`, evaluating `*p` will crash. So `select` **cannot** be used; a branch is required. You can verify for yourself that clang generates a branch here.

**This is the division of labour between `phi` and `select`:**

| | `phi` | `select` |
|---|---|---|
| Location | **Start** of a basic block | Anywhere in a block |
| Introduces control flow | Yes (together with `br`) | No |
| Are both paths evaluated | Only one is evaluated | Both are evaluated |
| Applies to | Side effects, possible faults, high cost | Pure computation |
| Source of the value | A **basic block** (predecessor) | A **value** |

Note the last row: the operands of `phi` are **basic block labels**, while the operands of `select` are **values**. This is the most essential difference between the two — `phi` is "cross-block", `select` is "within a block".

## 5.8 `switch`

C's `switch` uses the `switch` instruction:

```c
int switcher(int x) {
    switch (x) {
    case 0: return 10;
    case 1: return 20;
    case 2: return 30;
    case 7: return 70;
    default: return -1;
    }
}
```

`-O0`:

```llvm
define dso_local i32 @switcher(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 %0, ptr %3, align 4
  %4 = load i32, ptr %3, align 4
  switch i32 %4, label %9 [
    i32 0, label %5
    i32 1, label %6
    i32 2, label %7
    i32 7, label %8
  ]

5:                                                ; preds = %1
  store i32 10, ptr %2, align 4
  br label %10
...
9:                                                ; preds = %1
  store i32 -1, ptr %2, align 4
  br label %10

10:                                               ; preds = %9, %8, %7, %6, %5
  %11 = load i32, ptr %2, align 4
  ret i32 %11
}
```

The syntax:

```llvm
switch <type> <value>, label <default target> [
    <constant>, label <target>
    ...
]
```

`label %9` is the `default` branch, and the square brackets hold the individual cases. Note that the target of every case is a **constant**.

At `-O2`, `switch` gets optimized beautifully. The same code:

```llvm
@switch.table.switcher = private unnamed_addr constant [8 x i32] [i32 10, i32 20, i32 30, i32 -1, i32 -1, i32 -1, i32 -1, i32 70], align 4

define dso_local noundef i32 @switcher(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp ult i32 %0, 8
  br i1 %2, label %3, label %7

3:                                                ; preds = %1
  %4 = zext nneg i32 %0 to i64
  %5 = getelementptr inbounds [8 x i32], ptr @switch.table.switcher, i64 0, i64 %4
  %6 = load i32, ptr %5, align 4
  br label %7

7:                                                ; preds = %1, %3
  %8 = phi i32 [ %6, %3 ], [ -1, %1 ]
  ret i32 %8
}
```

LLVM turned the `switch` into a **table lookup**: it built an 8-element global array, put the values for case 0/1/2/7 straight into it, filled the holes with `-1` (that is, the value of default), and then completed the dispatch with one bounds check and one `load`.

Enjoy the use of `phi` here: `%8 = phi i32 [ %6, %3 ], [ -1, %1 ]` — if the table lookup succeeded, take the value from the table; if it is out of bounds, use `-1`. **This is a textbook case of "merging two paths with `phi`".**

(In `getelementptr inbounds [8 x i32], ptr @switch.table.switcher, i64 0, i64 %4` there are two indices: `i64 0` is "dereference this array pointer" and `i64 %4` is "take which element". Chapter 6 explains it in detail.)

## 5.9 A Handy By-product: Beyond `arith.select`, `abs` Becomes an Intrinsic

Incidentally, `abs_v` from Section 5.3 becomes this at `-O2`:

```llvm
define dso_local i32 @abs_v(i32 noundef %0) local_unnamed_addr #0 {
  %2 = tail call i32 @llvm.abs.i32(i32 %0, i1 true)
  ret i32 %2
}
```

It calls the `llvm.abs.i32` intrinsic directly. That belongs to Chapter 12; for now just get the impression that **the optimizer knows many mathematical patterns and replaces them with intrinsics**, because intrinsics have precise semantics and the backend can generate optimal instructions for a specific CPU.

## 5.10 Exercises

**Exercise 5.1** Hand-write an `.ll` file implementing `int max2(int a, int b)` using `br` + `phi`. Verify it with `llvm-as-18`, then run it with a C driver to confirm the result is correct.

**Exercise 5.2** Rewrite Exercise 5.1 to use `select`. Compare the two and explain why `select` is legal here.

**Exercise 5.3** Generate the `-O0` IR for `int classify(int x)` (returns -1 if less than 0, 0 if equal to 0, 1 if greater than 0). Count how many basic blocks there are and draw the CFG.

**Exercise 5.4** Deliberately write a `phi` whose predecessor blocks do not match, run `llvm-as-18`, and record the complete error message. Then fix it.

**Exercise 5.5 (key)** Take a function containing a `while` loop, generate its `-O0` IR, remove `optnone`, and run `opt-18 -passes=mem2reg -S`. Count how many `phi`s are produced and explain which C variable each one corresponds to.

**Exercise 5.6** Why can `a ? b : c` be optimized into `select` while `p ? *p : 0` cannot? Explain it in one sentence.

## 5.11 Summary

- A basic block is a sequence of instructions with a single entry and a single exit, ending with a **terminator** (`br`, `switch`, `ret`, `unreachable`).
- `br i1 %cond, label %a, label %b` is a conditional branch, and the condition is `i1`.
- **`phi` is a necessity of SSA**: when control flow merges and the same C variable has different values on different paths, the merge point needs `phi` to "select".
- Each operand of `phi` is a `[value, predecessor block]` pair, read as "coming from that block means taking this value".
- `phi` **does not execute** at run time; it is a compile-time wiring declaration.
- The predecessor block list of a `phi` must **exactly match** the real predecessors, otherwise the verifier reports an error.
- `select` is a within-block conditional selection that needs no control flow but requires both paths to be evaluated.
- **At `-O0` most variables live in memory, so `phi` is rare; when `mem2reg` promotes them to registers, `phi` appears.**

In the next chapter we enter the world of memory: `alloca`, `load`, `store`, and that headache-inducing `getelementptr`.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 4 Comparisons and the Tyranny of `i1`](04-ch04-comparisons-and-i1.md) · [Next: Chapter 6 Memory, Pointers and `getelementptr` →](06-ch06-memory-and-getelementptr.md)
