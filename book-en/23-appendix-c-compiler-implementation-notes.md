# Appendix C Compiler Implementation Notes

## C.0 Who this appendix is for

Chapters 15–20 of the main text follow the line "design → parse → code generation → control flow → walkthrough → testing" and present a complete implementation of a Lisp → LLVM IR compiler. To keep that line clear, some **in-depth discussion at the implementation level** has been moved here.

| Section | Content |
|---|---|
| [C.1](#c1-hybrid-strategy-ssa-for-parameters-stack-slots-for-let-hand-written-phi-for-if) | Which variable representation the generator actually uses |
| [C.2](#c2-why-if-can-emit-phi-by-hand-and-while-cannot) | The boundary within which hand-written `phi` works |
| [C.3](#c3-the-idle-ssa-machinery-in-irpy) | Which code is live and which is unused |
| [C.4](#c4-why-our-ir-after--o2-is-not-exactly-the-same-as-clangs) | The optimization gap caused by the missing `mustprogress` |
| [C.5](#c5-a-full-post-mortem-of-the-numbered-value-trap) | Why the generator cannot maintain numbering itself |

---

## C.1 Hybrid strategy: SSA for parameters, stack slots for `let`, hand-written `phi` for `if`

**This is the first thing to understand about the book's compiler.** Section 17.6 of the main text covers part of it; here is the complete version.

Our compiler uses **three different** representations for three kinds of thing:

| Thing | Representation | Why |
|---|---|---|
| Function parameters | **SSA values** (`%x`) | Immutable, use them directly |
| `let`-bound local variables | **Stack slots** (`alloca`) | Can be modified by `set` |
| **The value of an `if`** | **Hand-emitted `phi`** | The two branches' predecessors are **known**, so it can be written by hand |

Measuring that table (one compiler, five functions of different shapes):

```
alloca=0  phi=0   (defn f (x) x)                                               ; parameters only
alloca=0  phi=1   (defn f (x) (if (< x 0) 1 2))                               ; if only
alloca=1  phi=0   (defn f (x) (let ((y 1)) (+ x y)))                          ; let only
alloca=1  phi=0   (defn f (n) (let ((i 0)) (while (< i n) (set i (+ i 1))) i)) ; while only
alloca=1  phi=1   (defn f (x) (let ((y 1)) (if (< x 0) (set y 2) (set y 3)) y)) ; both
```

So:

- **`fib` has only parameters and `if`** → zero `alloca`s but **does** have a `phi` (the example in Chapter 19);
- **`sum_to` has `let` and `while`** → three `alloca`s and zero `phi`s (the example in Chapter 18).

**Both shapes coexist, and both are correct.**

---

## C.2 Why `if` can emit `phi` by hand and `while` cannot

This is the crux of the whole trade-off.

### `if`: the predecessors are known at compile time

```
        entry
        /    \
     then    else      <- once these two blocks are compiled, their end blocks are known
        \    /
        merge          <- both predecessors are known now, so the phi can be written on the spot
```

When the `then` branch is compiled, the block it ends up in is known (`then_end`); likewise for `else` (`else_end`). So at the merge block the compiler can write down **immediately**:

```llvm
%r = phi i32 [ %then_val, %then_end ], [ %else_val, %else_end ]
```

### `while`: the back edge is "the future"

```
    entry
      ↓
   while.cond  <------+   while compiling this block the back edge does not exist yet
      ↓  ↑            │
   while.body --------+   (the loop body has not been generated yet)
```

At the moment `while.cond` is compiled, the loop body **has not been generated yet**. Therefore:

- right now `while.cond` appears to have only one predecessor (the entry block);
- but the end of the loop body will immediately add a back edge, making it two predecessors;
- **if a `phi` is emitted at this point, it misses the predecessor that has not appeared yet** — the verifier reports `PHI node entries do not match predecessors!`

**This is exactly the "sealed block" problem**: a block's `phi` can only be completed once **all of its predecessors are known**. The merge block of an `if` has its predecessors determined once both branches are compiled; the cond block of a `while` has to wait until the loop body is compiled.

### Our two choices

| Case | Are the predecessors known? | What to do |
|---|---|---|
| The merge of an `if` | **Known at compile time** | Emit `phi` by hand |
| The cond of a `while` | **Unknown at compile time** | Put variables in stack slots, **no `phi` needed at all** |

**This division is not arbitrary; it corresponds exactly to "whether the predecessors are known".**

### By the way, that real error message

If you write the `phi`'s operands as "the branch's entry block" instead of "the branch's end block", you hit the trap below.

Here is a version that is easy to write wrong (the order of `branch` and `compile_expr` is reversed):

```python
fn.start(then_block)
fn.branch_placeholder(merge_ref)                    # <- emit the branch first
then_val = self.compile_expr(fn, env, then_expr)    # <- then compile the expression
```

This looks "neater" (finish the block first, then compile the contents), but it **is wrong**. Because `compile_expr` will:

1. move `current` into a new block (the `merge6` of a nested `if`);
2. leave `current` after the `phi` there.

So `branch_placeholder` is applied to `then1`, while `then_val` is computed in `merge6` — and `merge6` can never jump to the outer `merge3`. The verifier gives:

```
llvm-as-18: assembly parsed, but does not verify as correct!
PHI node entries do not match predecessors!
  %t5 = phi i32 [ %t2, %then1 ], [ %t4, %else2 ]
label %else2
label %merge6
Instruction does not dominate all uses!
  %t4 = phi i32 [ 0, %then4 ], [ 1, %else5 ]
  %t5 = phi i32 [ %t2, %then1 ], [ %t4, %else2 ]
```

**The fix**: move `branch` to **after** compiling the expression, and use `fn.current` rather than `then_block` as the `phi`'s operand:

```python
fn.start(then_block)
then_val = self.compile_expr(fn, env, then_expr)
then_end = fn.current                  # <- only known after compiling
fn.branch_placeholder(merge_ref)       # <- emit the branch now
```

### The lesson

> **"The current block" is implicit state that a nested compilation can modify.**

Compiling an expression does **not** guarantee a return to the original block. Any assumption that "the block is unchanged before and after compilation" is wrong.

There are two general solutions to this problem:

1. **Explicitly read back the current block** (what we do: `fn.current`);
2. **Do not share mutable state**; have `compile_expr` return `(value, end_block)`.

---

## C.3 The idle SSA machinery in `ir.py`

`ir.py` is implemented more generally than is currently needed. Specifically, the following code **is never used**:

| Code | Status |
|---|---|
| `Function.var(name, ty)` | Never called (the compiler uses `read_var` directly) |
| `Function.set_var(name, ty, v)` | Never called |
| `Function._read_variable` | Only called by `var` |
| `Function._add_phi_operand` | Same as above |
| `Function._complete_phi` | Only called by `seal_block` |
| `Function.seal_block` | Called in `op_while`, but the variables are all in memory, so it has nothing to do |
| `Function.materialize_phis` | Called by `render`, but no block contains a `phi` produced by this mechanism |
| The `Phi` class | Same as above |

This code implements the complete **sealed-block SSA construction algorithm** (Braun et al., *Simple and Efficient Construction of Static Single Assignment Form*). If it were actually used, the front end could route every variable through `var`/`set_var`, and would then **need no `alloca` at all**.

### Verifying that it really is idle

Add one print line inside `materialize_phis`:

```python
def materialize_phis(self):
    for block in self.blocks:
        phis = [
            (name, entry)
            for name, entry in block.bindings.items()
            if isinstance(entry, Phi)
        ]
        if not phis:
            continue
```

Insert `print("phi found", block.label)` before `if not phis: continue`, then compile `fib`, `classify`, and `sum_to`:

```bash
$ python3 compiler.py examples/fib.lisp > /dev/null   # no output
```

**There is no output at all.** Because the only `phi` in `fib` is the **text** emitted by hand by `op_if`, and it is not in `bindings`.

### Why keep it

1. **It demonstrates the complete SSA construction algorithm.** If you want to write a purely SSA front end, this is the starting point.
2. **`op_if` could have used it.** If the two branch values of an `if` were also brought into the variable table, there would be no need to emit `phi` by hand. Hand emission makes the flow **easier to see**; a general mechanism is more extensible.
3. **An honest architecture should permit unused abstractions.** A design in which all the code is used usually means the level of abstraction has been pushed too low.

**But the important thing is that the book tells you so explicitly.** Otherwise, reading the code, you would assume `seal_block` is on the critical path and spend time understanding a piece of logic that never actually runs.

---

## C.4 Why our IR after `-O2` is not exactly the same as clang's

Chapter 20 of the main text compared one result: after `-O2`, the `sum_to` we generate **still has its loop**; whereas clang's `-O2` output **eliminates the loop** and turns it into a closed-form formula.

### The root of the difference: attributes, not instructions

Look at the function header our generator produces:

```llvm
define i32 @l_sum_to(i32 %n) {
```

**No attributes at all.** And clang's:

```llvm
define dso_local i32 @sum_to(i32 noundef %0) local_unnamed_addr #0 {
```

```llvm
attributes #0 = { mustprogress nofree norecurse nosync nounwind willreturn memory(none) uwtable ... }
```

The key is **`mustprogress`**.

### What `mustprogress` is

It means:

> **This function is guaranteed to return within a finite number of steps and will not loop forever.**

That promise is **the necessary precondition for replacing a loop with a formula**. Because if "will the loop terminate" is itself uncertain, then "how long the loop runs" is observable behaviour of the program, and the optimizer may not change it.

**The C11 standard introduced the forward progress guarantee**, so clang can confidently put `mustprogress` on functions. Our Lisp compiler adds no attributes at all — so LLVM must conservatively assume "the loop may not terminate", and gives up on the closed form.

### Verifying this diagnosis

Add the attributes to our IR by hand:

```bash
sed 's/^define i32 @l_sum_to(i32 %n) {/define i32 @l_sum_to(i32 %n) mustprogress nounwind willreturn {/' sum.ll > sum_mp.ll
opt-18 -passes='default<O2>' -S sum_mp.ll | sed -n '/define/,/^}/p'
```

```llvm
define i32 @l_sum_to(i32 %n) local_unnamed_addr #0 {
entry0:
  %t2.not4 = icmp slt i32 %n, 1
  br i1 %t2.not4, label %while.end3, label %while.body2.preheader

while.body2.preheader:                            ; preds = %entry0
  %0 = add nuw i32 %n, 1
  %smax = tail call i32 @llvm.smax.i32(i32 %0, i32 2)
  %1 = shl nuw i32 %smax, 1
  %2 = add nsw i32 %smax, -2
  %3 = zext nneg i32 %2 to i33
  %4 = add nsw i32 %smax, -3
  %5 = zext i32 %4 to i33
  %6 = mul i33 %3, %5
  %7 = lshr i33 %6, 1
  %8 = trunc i33 %7 to i32
  %9 = add i32 %1, %8
  %10 = add i32 %9, -3
  br label %while.end3

while.end3:                                       ; preds = %while.body2.preheader, %entry0
  %s.addr.0.lcssa = phi i32 [ 0, %entry0 ], [ %10, %while.body2.preheader ]
  ret i32 %s.addr.0.lcssa
}
```

**The loop is gone and `i33` appears** — the same shape as clang's. And it computes the right answer:

```bash
$ opt-18 -passes='default<O2>' -S sum_mp.ll -o sum_mp_o2.ll
$ llvm-as-18 sum_mp_o2.ll -o sum_mp_o2.bc
$ clang-18 -w driver.c sum_mp_o2.bc -o t && ./t
0 55 500500
```

(`0 55 500500` is exactly the correct answer for `sum_to(0)`, `sum_to(10)`, and `sum_to(1000)`.)

### The general significance of this finding

**One attribute is all the difference.**

It demonstrates precisely the boundary of responsibility between front end and backend:

| Concern | Who is responsible |
|---|---|
| Semantic correctness (computing the right answer) | **The front end** |
| Promoting mutable variables to SSA | LLVM (`mem2reg`) |
| **Telling LLVM "the loop definitely terminates"** | **The front end** (adding `mustprogress`) |
| Loop closed-forming, vectorization, inlining | LLVM |

**`mustprogress` is information about the source language's semantics**, and only the front end knows it. LLVM cannot infer it on its own — because a language that permits infinite loops **cannot** declare `mustprogress`.

**So should our compiler add it?** No. Because our language specification does **not** say loops must terminate, and adding it would be a lie. There are two honest options:

1. **Add to the language specification** that "all loops must terminate within a finite number of steps, otherwise the behaviour is undefined" — the same as C11's forward progress; or
2. **Stay silent** and accept the loss of optimization opportunity.

This book chooses option 2 and records the trade-off explicitly here.

### So what exactly did our compiler achieve

**What it achieved** (all measured):

- The generated IR **passes the LLVM verifier** (22/22 end-to-end tests);
- After `mem2reg`, every memory operation in `sum_to` disappears, producing a **`phi` structure isomorphic to clang's**;
- The generated programs **behave correctly** under `-O1`/`-O2`/`-O3`;
- With `mustprogress` added, it reaches **the same optimization result as clang**.

**What it did not achieve**:

- **It generates no function attributes by default**, so LLVM optimizes more conservatively than it does for clang;
- It does no type inference, gives no inlining hints, and generates no attributes such as `noundef`.

**But this does not affect the core conclusion**:

> **A front end of about 500 lines that translates semantics correctly into IR can let LLVM's optimizer do the great majority of the work.** The small remaining gap is the absence of **source-language semantic information**, not a gap in the quality of IR generation.

---

## C.5 A full post-mortem of the numbered-value trap

Chapter 8 of the main text explained LLVM's numbering rules, and Chapter 17 mentioned "do not use numbered values". Here is the complete version.

### The naive implementation

```python
class Function:
    def __init__(self):
        self.temp_counter = 0

    def new_temp(self):
        self.temp_counter += 1
        return f"%{self.temp_counter}"        # <- uses numbered values
```

The idea is: "I will count for myself; the first temporary is `%1`, the second is `%2`, …"

### Why it fails

Because the numbering counter is **shared** among **parameters, anonymous basic blocks, and instructions with results** (Chapter 8 of the main text). And the generator inserts a great many basic blocks while generating:

```python
then_block = fn.new_block("then")     # the generator thinks this is just a name
```

If the generator uses **numbered labels**, or uses `%{counter}` for temporaries, its counter will drift out of step with LLVM's real counter. The error looks like this:

```llvm
; numfail.ll
define i32 @l_ack(i32 %m, i32 %n) {
entry:
  %1 = icmp eq i32 %m, 0
  br i1 %1, label %2, label %3
2:
  %6 = add i32 %n, 1
  ret i32 %6
3:
  %4 = sub i32 %m, 1        ; <- numbering goes backwards from %6 to %4
  ret i32 %4
}
```

```bash
$ llvm-as-18 numfail.ll -o /dev/null
llvm-as-18: numfail.ll:8:1: error: label expected to be numbered '7' or greater
3:
^
```

The source file lives at `code/part2-ir/numfail.ll` (together with the other "deliberately wrong" examples).

How to read it: the generator thought "`%4` is next", but LLVM's counter had already climbed to 12.

### Why this bug is especially hard to track down

Because it **does not error every time**. The rule for numbered values is "must be monotonically increasing, **skipping numbers is allowed**". So:

- when the generator's counter is **too small**, you get an error (as above);
- when it is **too large**, **there is no error**:

```llvm
define i32 @f(i32 %x) {
entry:
  %5 = add i32 %x, 1       ; skips %1..%4, LLVM accepts it
  ret i32 %5
}
```

**This passes verification.** But the numbering is out of step with the actual structure, and later, when you want to insert an instruction somewhere, you will find that "there is no number available".

**Worse still**: if the generator mixes numbered labels with named labels, some functions pass and some do not, and the reported error location points at a place you never wrote.

### The solution: use named values throughout

```python
def new_temp(self):
    """Allocate a new *named* temporary."""
    self.temp_counter += 1
    return f"%t{self.temp_counter}"
```

It generates:

```llvm
define i32 @l_fib(i32 %n) {
entry0:
  %t1 = icmp slt i32 %n, 2
  br i1 %t1, label %then1, label %else2
```

**The parameters are named values, the temporaries are named values, the block labels are named values — there is no numbered value anywhere, and the rules simply do not apply.**

### The lesson

> **Do not deal with implicit rules you do not fully understand.**

Spending time to simulate LLVM's numbering rules exactly is an **unnecessary** burden. Named values cost a few extra characters and buy you:

- it is impossible to fail because the counter drifted out of step;
- the generated IR is more readable (`%t1` clearly marks "this is a temporary produced by the front end");
- when debugging, you can see at a glance which value was produced by whom.

**This is not "working around" the rule, but an engineering choice made after understanding it.**

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Appendix B Optimization Primer: From `-O0` to `-O2`](22-appendix-b-optimization-primer.md) · [Next: Appendix D LLVM IR Instruction Quick Reference →](24-appendix-d-instruction-quick-reference.md)
