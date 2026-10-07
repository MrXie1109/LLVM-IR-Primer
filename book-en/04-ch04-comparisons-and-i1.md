# Chapter 4 Comparisons and the Tyranny of `i1`

## 4.1 A strange type: `i1`

Let us start with the shortest example:

```c
int lt(int a, int b) { return a < b; }
```

`clang-18 -S -emit-llvm -O2`:

```llvm
define dso_local i32 @lt(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = icmp slt i32 %0, %1
  %4 = zext i1 %3 to i32
  ret i32 %4
}
```

Two new things have appeared: `icmp` and `i1`.

`icmp` is **integer comparison** (**i**nteger **cmp**). Its result type is `i1` — an integer **only 1 bit wide**, whose value can only be 0 or 1.

**Why is a 1-bit integer type needed?** Because the result of a comparison is inherently two-valued: true or false. If `icmp` returned `i32` directly, the back end would have to deal with the extra question of "how to stuff it into 32 bits"; if a dedicated `bool` type were introduced, the type system would gain another special case. `i1` is a beautiful compromise: **it is just an integer type, only with a width of 1**. So all the integer rules apply automatically — you can do `and`, `or`, `xor`, and even `add` on `i1`.

## 4.2 A comparison result must be "widened" before it can be used as an `int`

In C, the result type of `a < b` is `int`, with value 0 or 1. In IR, `icmp` gives `i1`. One conversion is needed in between:

```llvm
  %4 = zext i1 %3 to i32
```

`zext` is **zero extension** (**z**ero **ext**end): it pads the high bits of a narrow integer with 0 to widen it. Extending `i1`'s `1` to `i32` gives `0x00000001`, that is, 1; extending `0` still gives 0. This is exactly the semantics C requires.

What about C's `_Bool`? Then no `zext` is needed, because `_Bool` is directly `i1` in IR:

```c
_Bool tobool(int x) { return x != 0; }
```

```llvm
define dso_local noundef zeroext i1 @tobool(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp ne i32 %0, 0
  ret i1 %2
}
```

Note that the return value attribute is `zeroext` — because in the x86-64 calling convention, an `i1` return value is placed into the 8-bit register `al`, and the caller only guarantees that the low bits of `al` are valid, so the function must guarantee that the high bits are 0.

## 4.3 Six comparison predicates × two signednesses

`icmp`'s first argument is the **comparison predicate**, which determines how the comparison is done. This is the core table of this chapter:

| C spelling (signed) | Predicate | C spelling (unsigned) | Predicate |
|---|---|---|---|
| `a < b` | `icmp slt` | `a < b` | `icmp ult` |
| `a <= b` | `icmp sle` | `a <= b` | `icmp ule` |
| `a > b` | `icmp sgt` | `a > b` | `icmp ugt` |
| `a >= b` | `icmp sge` | `a >= b` | `icmp uge` |
| `a == b` | `icmp eq` | `a == b` | `icmp eq` |
| `a != b` | `icmp ne` | `a != b` | `icmp ne` |

The naming rule is very tidy: **`s`**igned / **`u`**nsigned + **`lt`** (less than) / **`le`** / **`gt`** / **`ge`** / **`eq`** / **`ne`**.

Note that `eq` and `ne` have **no** `s`/`u` variants — equality is bitwise equality, independent of signedness.

Let us verify completely:

```c
int lt(int a, int b)  { return a < b; }
int le(int a, int b)  { return a <= b; }
int gt(int a, int b)  { return a > b; }
int ge(int a, int b)  { return a >= b; }
int eq(int a, int b)  { return a == b; }
int ne(int a, int b)  { return a != b; }
int ult(unsigned a, unsigned b) { return a < b; }
```

`-O2` output (excerpting only the comparison line in each):

```llvm
  %3 = icmp slt i32 %0, %1        ; lt
  %3 = icmp sle i32 %0, %1        ; le
  %3 = icmp sgt i32 %0, %1        ; gt
  %3 = icmp sge i32 %0, %1        ; ge
  %3 = icmp eq i32 %0, %1         ; eq
  %3 = icmp ne i32 %0, %1         ; ne
  %3 = icmp ult i32 %0, %1        ; ult
```

Each is followed by `zext i1 %3 to i32`.

> **Verify it yourself**: you can write a small program to measure the difference between `ult` and `slt` on the same pair of inputs. `-1` as an unsigned number is 4294967295, so `(unsigned)-1 < 1` is false, while `-1 < 1` is true. At the IR level they use the same `i32` type and different predicates — which once again confirms the conclusion of Chapter 3: **signedness is not in the type, it is in the operation**.

## 4.4 The tyranny of `i1`: it rules all control flow

`i1` matters not only because of comparisons. **In LLVM, every conditional branch must be conditioned on an `i1`**:

```llvm
br i1 %cond, label %then, label %else
```

Here `%cond` must be `i1`. It cannot be `i32`, it cannot be `ptr`. This is why the title calls it a "tyranny": **any notion of "true or false" in your source language must ultimately be translated into `i1`.**

This imposes a task that runs through the entire front end: **reduce every "truth value" to `i1`**. In C, `if (p)` (p is a pointer), `if (x)` (x is an int), and `if (d)` (d is a double) are all legal, but IR's `br` accepts only `i1`. So an explicit conversion is needed:

| C condition | How to convert |
|---|---|
| `if (x)`, `x` is `int` | `%c = icmp ne i32 %x, 0` |
| `if (p)`, `p` is `ptr` | `%c = icmp ne ptr %p, null` |
| `if (d)`, `d` is `double` | `%c = fcmp one double %d, 0.0` |
| `if (b)`, `b` is `_Bool`/`i1` | Used directly; it is already `i1` |

When comparing a pointer with `null`, `icmp ne ptr %p, null` is a very common pattern. Measured:

```c
int deref_or_zero(int *p) { return p ? *p : 0; }
```

Under `-O2`:

```llvm
define dso_local i32 @deref_or_zero(ptr noundef readonly %0) local_unnamed_addr #0 {
  %2 = icmp eq ptr %0, null
  br i1 %2, label %5, label %3

3:                                                ; preds = %1
  %4 = load i32, ptr %0, align 4, !tbaa !5
  br label %5

5:                                                ; preds = %1, %3
  %6 = phi i32 [ %4, %3 ], [ 0, %1 ]
  ret i32 %6
}
```

`%2 = icmp eq ptr %0, null` — note that `null` is IR's null-value keyword for pointers. Here clang chose to use `eq` together with swapping the two branches, rather than `ne`; the two are equivalent, and it is merely a preference of the code generator. Chapter 10 covers the details of `null`.

(`!tbaa !5` is metadata used for alias analysis; Chapter 12 discusses it. The `readonly` attribute is clang's inference that "this function does not write memory through that pointer.")

## 4.5 `&&` and `||` need control flow, not `and`/`or`

This is the mistake beginners make most often. C's `&&` has **short-circuit semantics**: in `a && b`, when `a` is false, `b` is **not** evaluated. If `b` has side effects (say `f()`), short-circuiting or not changes the program's behaviour directly.

So `&&` **cannot possibly** be translated into `and i32 %a, %b`. It must be implemented with branches. Measured:

```c
int logic_and(int a, int b) { return a && b; }
int logic_or(int a, int b)  { return a || b; }
int logic_not(int a)        { return !a; }
```

Under `-O0`:

```llvm
define dso_local i32 @logic_and(i32 noundef %0, i32 noundef %1) #0 {
  ...
  %5 = load i32, ptr %3, align 4
  %6 = icmp ne i32 %5, 0
  br i1 %6, label %7, label %10
7:                                                ; preds = %2
  %8 = load i32, ptr %4, align 4
  %9 = icmp ne i32 %8, 0
  br label %10
10:                                               ; preds = %7, %2
  %11 = phi i1 [ false, %2 ], [ %9, %7 ]
  %12 = zext i1 %11 to i32
  ret i32 %12
}
```

Look carefully at this code; it is an excellent specimen for understanding short-circuit evaluation:

1. `%6 = icmp ne i32 %5, 0` — converts `a` into an `i1`.
2. `br i1 %6, label %7, label %10` — **only if `a` is true do we go and evaluate `b`** (jump to `%7`); otherwise we **jump straight to `%10`**, and `b` is not touched at all. This is the short circuit.
3. `%9 = icmp ne i32 %8, 0` — this is the truth value of `b`, computed only in `%7`.
4. `%11 = phi i1 [ false, %2 ], [ %9, %7 ]` — the merge point. If we came from `%2` (`a` is false), the result is `false`; if we came from `%7`, the result is the truth value of `b`.

`false` and `true` are IR's boolean constants. `||` is completely symmetric, only the constants are the other way round:

```llvm
  %11 = phi i1 [ true, %2 ], [ %9, %7 ]
```

`!a` needs no branch (it does not short-circuit), so it can be computed directly:

```llvm
  %4 = icmp ne i32 %3, 0
  %5 = xor i1 %4, true
```

`xor i1 %4, true` is logical negation: `0 xor 1 = 1`, `1 xor 1 = 0`. Very clean.

**Remember this correspondence:**

| C | IR under `-O0` | IR under `-O2` (when the operands have no side effects) |
|---|---|---|
| `a & b` | `and i32 %a, %b` (one instruction) | Same as left |
| `a && b` | `br` + `phi i1` (at least one branch) | May be optimized into `and i1` |
| `a \| b` | `or i32 %a, %b` (one instruction) | Same as left |
| `a \|\| b` | `br` + `phi i1` | May be optimized into `or i1` |

### An important correction: `&&` under `-O2`

The `-O0` output above really does have a branch. But if you compile the same `logic_and` with `-O2`, you will see:

```llvm
define dso_local noundef i32 @logic_and(i32 noundef %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = icmp ne i32 %0, 0
  %4 = icmp ne i32 %1, 0
  %5 = and i1 %3, %4
  %6 = zext i1 %5 to i32
  ret i32 %6
}
```

The branch **has disappeared**, replaced by `and i1 %3, %4`.

This looks like a violation of "short-circuit semantics," but it is actually **perfectly legal**. The key point is: `%1` is merely a **parameter**, and reading it has no side effects whatsoever (it cannot crash, cannot do IO, cannot loop forever). Since "not evaluating `b`" and "evaluating `b`" make no difference to the program's observable behaviour, the optimizer is free to compute both and then `and` them.

**The optimizer is not ignoring the short-circuit rule; it is proving that here the short circuit is unobservable.** If `b` is replaced by `f()`:

```c
int a_side_effect(int a) { return a && f(); }
```

then `-O2` **must** keep the branch, because "not calling `f()`" and "calling `f()`" are an observable difference. You can verify this yourself — it is an excellent exercise for understanding "what can be optimized and what cannot" (see Exercise 4.2).

This lesson has general significance: **the IR structure you see under `-O0` (branches, `phi`, memory operations) may be completely rewritten under `-O2`. To judge whether an optimization is legal, always ask "does the source language's semantics permit this change," not "what does the book say this kind of code should look like."**

## 4.6 Floating-point comparison: `fcmp` and its pile of predicates

Floating-point comparison uses `fcmp`, and it has many more predicates than the integer case, because `NaN` has to be handled.

```c
int fcmp_lt(double a, double b) { return a < b; }
```

```llvm
define dso_local i32 @fcmp_lt(double noundef %0, double noundef %1) local_unnamed_addr #0 {
  %3 = fcmp olt double %0, %1
  %4 = zext i1 %3 to i32
  ret i32 %4
}
```

`fcmp olt` — the `o` is the prefix for **o**rdered, meaning "perform this comparison **only when neither operand is NaN**."

Why is this prefix needed? Because IEEE 754 specifies: **any comparison with NaN (except `!=`) returns false**. `fcmp`'s predicates need to express this rule precisely:

| Predicate | Meaning |
|---|---|
| `false` | Always false |
| `oeq` | Ordered and equal |
| `ogt` / `oge` / `olt` / `ole` | Ordered and >, >=, <, <= |
| `one` | Ordered and not equal |
| `ord` | Ordered (neither is NaN) |
| `ueq` / `ugt` / `uge` / `ult` / `ule` | **Unordered or** the corresponding comparison (u = unordered) |
| `une` | Unordered or not equal |
| `uno` | Unordered (at least one is NaN) |
| `true` | Always true |

C's `<` corresponds to `olt` (because C's `<` must return false when NaN is involved, which is exactly "ordered and less than").

There is a famous trap: C's `a != b` corresponds to **`une`**, not `one`. Because under IEEE, NaN != NaN is **true**, and `une` is precisely "unordered or not equal." You can verify it yourself:

```c
int fcmp_ne(double a, double b) { return a != b; }
```

## 4.7 Exercises

**Exercise 4.1** Generate the IR for `int ult_test(unsigned a, unsigned b) { return a >= b; }` and confirm that the predicate is `uge`.

**Exercise 4.2** Compile `logic_and` with `-O2` and see whether the short-circuit branch is still there. Why **can't** the optimizer simply remove it? (Hint: `b` might be a function call.)

**Exercise 4.3** Write a C function for which clang generates `fcmp uno`. Hint: think of an expression meaning "at least one of them is NaN," such as `a != a`.

**Exercise 4.4** Verify the following statement, then explain it: **"The result of `icmp` is always `i1`, even when what is compared is an `i64` or a `ptr`."**

**Exercise 4.5 (thought question)** Why does LLVM not simply have `icmp` return `i32`, saving all the `zext`s?

## 4.8 Summary

- `icmp` does integer comparison and its result is `i1`; `fcmp` does floating-point comparison and its result is also `i1`.
- The predicates encode **signedness** (`s`/`u`) and **orderedness** (`o`/`u`).
- `eq`/`ne` have no signed variants; floating-point `!=` requires `une`.
- Every conditional branch `br i1` requires an `i1`, so a front end must reduce all kinds of truth values to `i1`.
- `&&` and `||` need `br` + `phi`; they cannot be compiled into `and`/`or`.
- `!a` can be compiled into `xor i1 %a, true`.

In the next chapter we go deep into control flow and properly meet `phi` — the most important instruction in the whole book.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 3 Arithmetic, Logic and Shifts](03-ch03-arithmetic-logic-and-shifts.md) · [Next: Chapter 5 Control Flow: `br`, Basic Blocks and `phi` →](05-ch05-control-flow-and-phi.md)
