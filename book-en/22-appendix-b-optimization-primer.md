# Appendix B Optimization Primer: From `-O0` to `-O2`

## B.0 Who this appendix is for

The main text follows the line "read IR → write IR" and mentions optimization only where necessary. But one class of question keeps coming up:

> **"Why is my IR so bloated?" "What does `-O2` actually do?" "Why does running `opt` do nothing?"**

These questions are all natural; they just do not belong to any single chapter. This appendix gathers them and organizes them in the order "from symptom to principle".

| Section | The question it answers |
|---|---|
| [B.1](#b1-why-alloca-disappears-mem2reg) | How do `alloca`/`load`/`store` disappear |
| [B.2](#b2-why-running-opt-does-nothing-optnone) | Why `opt` has no effect on my IR |
| [B.3](#b3-witnessing-the-birth-of-phi) | Where the `phi`s in a loop come from |
| [B.4](#b4-nsw-and-nuw-what-power-they-give-the-optimizer) | What flags like `nsw` are actually worth |
| [B.5](#b5-seeing-the-optimization-pipeline-clearly) | Which passes `-O1/-O2/-O3` contain |
| [B.6](#b6-watching-pass-by-pass-a-complete-experiment) | Watching IR transform step by step |
| [B.7](#b7-a-misconception-that-must-be-cleared-up) | "`clang -O2`" ≠ "`opt -O2` on `-O0` output" |
| [B.8](#b8-debugging-the-ir-during-optimization) | `-print-after-all` and friends |

---

## B.1 Why `alloca` disappears: `mem2reg`

Chapter 2 of the main text explained: under `-O0` every C local variable gets its own `alloca` slot. In optimized IR those slots are all gone.

The pass that does this is called **`mem2reg`** (memory to register). Its condition is:

> **If a slot created by `alloca` never has its address taken (no `&x`-style operation) and all of its reads and writes can be analysed, promote that slot to an SSA value** — inserting `phi` nodes automatically where needed.

Look at a minimal example:

```c
int mul_add(int x, int y, int z) {
    return x * y + z;
}
```

`-O0` (12 instructions in the function body):

```llvm
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
```

Run `mem2reg` once (note that you must first remove `optnone`, see [B.2](#b2-why-running-opt-does-nothing-optnone)):

```bash
clang-18 -S -emit-llvm -O0 mul_add.c -o mul_add.O0.ll
sed 's/ optnone//' mul_add.O0.ll > mul_add.nooptnone.ll
opt-18 -passes=mem2reg -S mul_add.nooptnone.ll -o -
```

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  %4 = mul nsw i32 %0, %1
  %5 = add nsw i32 %4, %2
  ret i32 %5
}
```

**12 instructions → 3.** Every `alloca`/`store`/`load` has vanished and the parameters feed straight into the arithmetic.

**This is where the "three lines of IR" from `-O2` come from.** Chapter 2 of the main text stressed this: tutorials that announce "`mul_add` is just three lines" leave out the precondition — that is what it looks like under `-O2`.

### Why does `-O0` not generate those three lines directly?

Because of two requirements:

1. **Debugging experience** — the parameters go into stack slots so that gdb can show them at any point during the function's execution;
2. **Simplicity of the generator** — putting mutable variables in memory means the code generator does not need to do dominance analysis (see [B.3](#b3-witnessing-the-birth-of-phi) for details).

The cost is redundant reads and writes at runtime, and `mem2reg` removes them for free. This is clang's `-O0` strategy, and it is also the strategy of the compiler in Part 3 of this book.

---

## B.2 Why running `opt` does nothing: `optnone`

**This is the point that confuses beginners the most.** You ran what the tutorial said:

```bash
opt-18 -passes=mem2reg -S mul_add.O0.ll -o -
```

**The output is identical to the input.** It is not that `mem2reg` is broken; the function header carries `optnone`:

```llvm
; Function Attrs: noinline nounwind optnone uwtable
define dso_local i32 @mul_add(...) #0 {
```

`optnone` means "**do not optimize this function**". It is explicitly required by `-O0`, in order to make the debugging experience predictable. **Any pass that sees it skips straight past, and gives no hint at all.**

Remove `optnone` and everything works:

```bash
sed 's/ optnone//' mul_add.O0.ll > mul_add.nooptnone.ll
opt-18 -passes=mem2reg -S mul_add.nooptnone.ll -o -
```

**Troubleshooting list**: if you run `opt` on `-O0`-generated IR and nothing changes, check in this order:

1. Is there an `optnone` near the function? (`grep optnone file.ll`)
2. Was the whole module compiled with `-O0`?
3. If you generated the IR yourself, did your generator add unnecessary attributes?

---

## B.3 Witnessing the birth of `phi`

Chapter 5 of the main text explained what `phi` is. Here we answer a follow-up question: **the `-O0` loop clearly has no `phi`, so when do they appear?**

```c
int sum_to(int n) {
    int s = 0;
    for (int i = 1; i <= n; i++)
        s += i;
    return s;
}
```

Take the `-O0` IR, remove `optnone`, and run `mem2reg`:

```bash
sed 's/ optnone//' sum_to.O0.ll > sum_to.nooptnone.ll
opt-18 -passes=mem2reg -S sum_to.nooptnone.ll -o -
```

```llvm
define dso_local i32 @sum_to(i32 noundef %0) #0 {
  br label %2

2:                                                ; preds = %6, %1
  %.01 = phi i32 [ 0, %1 ], [ %5, %6 ]
  %.0 = phi i32 [ 1, %1 ], [ %7, %6 ]
  %3 = icmp sle i32 %.0, %0
  br i1 %3, label %4, label %8

4:                                                ; preds = %2
  %5 = add nsw i32 %.01, %.0
  br label %6

6:                                                ; preds = %4
  %7 = add nsw i32 %.0, 1
  br label %2

8:                                                ; preds = %2
  ret i32 %.01
}
```

**Two `phi`s have appeared.**

```llvm
2:                                                ; preds = %6, %1
  %.01 = phi i32 [ 0, %1 ], [ %5, %6 ]
  %.0 = phi i32 [ 1, %1 ], [ %7, %6 ]
```

Reading the first one word by word: the value of `s` (the accumulator) in block `%2` is —

- coming from `%1` (the entry): `0` (the initial value);
- coming from `%6` (the increment block): `%5` (the sum newly computed this round).

The second one works the same way: `i` is `1` from the entry and `%7` (`i + 1`) from `%6`.

**This is the entire reason `phi` exists.** A variable repeatedly modified inside a loop must, in SSA, be renamed into multiple values along multiple paths, and the merge point needs a mechanism to decide which one to take — `phi` is that mechanism.

And the whole process is **automatic**: you do not need to write dominance-tree analysis by hand; as long as the variable's address is never taken and its read/write pattern is analysable, `mem2reg` does it for you.

**This also explains the dilemma of the Part 3 compiler**: emitting `phi` by hand is very hard for loops, because a loop's **back edge only appears in the future** (see [Appendix C.2](23-appendix-c-compiler-implementation-notes.md#c2-why-if-can-emit-phi-by-hand-and-while-cannot)). Putting variables in memory sidesteps the problem entirely.

---

## B.4 `nsw` and `nuw`: what power they give the optimizer

Chapter 3 of the main text explained that `nsw` is the promise "signed overflow means poison". Here we look at **what it is concretely worth**.

### Example one: eliminating the conditional entirely

```c
int f(int x) {
    if (x + 1 > x) return 1;
    return 0;
}
```

Mathematically `x + 1 > x` always holds, but for `x = INT_MAX`, `x + 1` is UB in C. Since the programmer guarantees it will not happen, the compiler may assume it never happens:

```bash
clang-18 -S -emit-llvm -O2 f.c -o -
```

```llvm
define dso_local noundef i32 @f(i32 noundef %0) local_unnamed_addr #0 {
  ret i32 1
}
```

**The whole function folds to `ret i32 1`.** This optimization is legal precisely because `add nsw` tells the optimizer "on overflow the result is poison, and I do not care".

### Turning that assumption off with `-fwrapv`

`-fwrapv` tells clang "signed overflow must wrap, it is not UB":

```bash
clang-18 -S -emit-llvm -O2 -fwrapv f.c -o -
```

```llvm
define dso_local noundef i32 @f(i32 noundef %0) local_unnamed_addr #0 {
  %2 = icmp ne i32 %0, 2147483647
  %3 = zext i1 %2 to i32
  ret i32 %3
}
```

The function no longer always returns 1; it becomes "return 1 if `x != INT_MAX`, otherwise return 0" — the correct answer under wrapping semantics.

**The same C source, one compiler option, two completely different pieces of IR and two different semantics.**

### Example two: strength reduction

```c
int p2(int a) { return a * 2; }
int p3(int a) { return a * 3; }
int p4(int a) { return a * 4; }
```

`-O2`:

```llvm
%2 = shl nsw i32 %0, 1        ; p2: multiplication becomes a shift
%2 = mul nsw i32 %0, 3        ; p3: not a power of two, stays a multiply
%2 = shl nsw i32 %0, 2        ; p4
```

**Note that the `shl` also carries `nsw`.** Shifting left by one really can overflow, and the overflow semantics must stay consistent with the original `mul`, otherwise the optimization would change the semantics. That `nsw` is inherited from `mul nsw` — **it has to be passed on honestly**.

### Example three: unsigned division becomes a shift, signed division does not

```c
int div4(int a) { return a / 4; }
unsigned div4u(unsigned a) { return a / 4; }
```

Measured under `-O2`:

```llvm
define dso_local noundef i32 @div4(i32 noundef %0) local_unnamed_addr #0 {
  %2 = sdiv i32 %0, 4          ; signed: stays a division
  ret i32 %2
}

define dso_local noundef i32 @div4u(i32 noundef %0) local_unnamed_addr #0 {
  %2 = lshr i32 %0, 2          ; unsigned: becomes a logical shift
  ret i32 %2
}
```

**Why can the signed one not be swapped?** Because **signed division rounds toward zero, while arithmetic right shift rounds toward negative infinity**, and the two differ for negative numbers:

```
-7 / 4  = -1     (truncates toward zero)
-7 >> 2 = -2     (rounds down, fills the sign bit)
```

Since the results differ, the optimizer cannot replace `sdiv` with `ashr`. Unsigned division, on the other hand, **is** rounding toward negative infinity, exactly matching `lshr`, so it can be replaced safely.

This explains why flags such as `nsw`/`nuw`/`exact` are so valuable: **they tell the optimizer when a replacement is allowed.** For example, if we could prove `%0` is non-negative (via `nneg` or range metadata), a signed `sdiv` could become a shift too.

---

## B.5 Seeing the optimization pipeline clearly

### What `-O0` through `-O3` each are

`--print-pipeline-passes` prints out the complete pass list for a given optimization level:

```bash
opt-18 -passes='default<O2>' --print-pipeline-passes /dev/null
```

(`default<O0>` prints one extra line on **stderr**: `Could not parse dumped pass pipeline: unknown module pass 'BitcodeWriterPass'`, because the `BitcodeWriterPass` at the end of that pipeline cannot be re-parsed. It is a harmless notice and the pipeline itself is still printed on stdout as usual. To silence it, redirect stderr away, as in `2>/dev/null`.)

The output is long, but comparing the beginnings is already informative.

**`default<O0>`:**

```
always-inline,coro-cond(coro-early,cgscc(coro-split),coro-cleanup,globaldce),function(annotation-remarks),verify,BitcodeWriterPass
```

**`default<O1>` / `default<O2>` / `default<O3>`:**

```
annotation2metadata,forceattrs,inferattrs,coro-early,function<eager-inv>(
  lower-expect,simplifycfg<...>,sroa<modify-cfg>,early-cse<>),openmp-opt,
  ipsccp,called-value-propagation,globalopt,function<eager-inv>(
  mem2reg,instcombine<...>,simplifycfg<...>),always-inline,...
```

**The key comparison**: `default<O0>` has **no `mem2reg`**; `default<O1>` does.

This also clears up a common misunderstanding: **the `alloca` in `-O0` output is not "left behind by the optimizer" but generated deliberately by the clang front end.** The `-O0` optimization pipeline is nearly empty — it only does what has to be done (coroutine cleanup, verification).

### The difference between `-O1` / `-O2` / `-O3`

The first half of the three levels is almost identical; the differences are mainly in the second half:

| Level | Typical additions |
|---|---|
| `-O1` | `mem2reg`, `instcombine`, `simplifycfg`, some inlining |
| `-O2` | Loop optimizations (`licm`, `loop-rotate`, `indvars`), vectorization attempts, more aggressive inlining |
| `-O3` | `loop-unroll<O3>`, more vectorization, a higher inlining threshold |

The passes `-O3` has in addition to `-O1`, as measured (excerpt):

```bash
opt-18 -passes='default<O1>' --print-pipeline-passes /dev/null | tr ',' '\n' | sort -u > o1.txt
opt-18 -passes='default<O3>' --print-pipeline-passes /dev/null | tr ',' '\n' | sort -u > o3.txt
comm -13 o1.txt o3.txt
```

```
aggressive-instcombine
argpromotion
constraint-elimination
correlated-propagation
dse
early-cse<>
gvn<>
jump-threading
loop-unroll<O3>
loop-vectorize<no-interleave-forced-only;no-vectorize-forced-only;>
```

**`loop-unroll<O3>` and `loop-vectorize` are the core additions of `-O3`**: more aggressive loop unrolling and automatic vectorization. This also explains why `-O3` is sometimes slower — it trades code size and instruction-cache hit rate for throughput.

### The syntax of pipeline strings

```bash
opt-18 -passes=mem2reg -S in.ll -o -                  # a single pass
opt-18 -passes='instcombine,simplifycfg' -S in.ll -o -  # a comma-separated sequence
opt-18 -passes='function(mem2reg)' -S in.ll -o -       # an explicit scope
opt-18 -passes='default<O2>' -S in.ll -o -             # a predefined pipeline
```

| Scope | Meaning |
|---|---|
| `module(...)` | Module level (can see the whole module) |
| `cgscc(...)` | Call-graph SCC level (inlining and so on) |
| `function(...)` | Function level (`mem2reg` is at this level) |
| `loop(...)` | Loop level |
| `loop-mssa(...)` | Loop passes that need MemorySSA |

---

## B.6 Watching pass by pass: a complete experiment

Take `sum_to` as the experiment and watch it transform step by step.

### Step 0: the original `-O0` (with memory operations)

See the example in [B.1](#b1-why-alloca-disappears-mem2reg). At this point it is `alloca` + `load`/`store`, with **zero `phi`s**.

### Step 1: `mem2reg`

See [B.3](#b3-witnessing-the-birth-of-phi). All memory operations disappear and **two `phi`s appear**.

### Step 2: add `instcombine`

```bash
opt-18 -passes='mem2reg,instcombine' -S sum_to.nooptnone.ll -o -
```

`instcombine` performs local algebraic simplification. It changes little for this example, but has a striking effect on other code.

### Step 3: the full `-O2`

```bash
opt-18 -passes='default<O2>' -S sum_to.nooptnone.ll -o -
```

```llvm
define dso_local i32 @sum_to(i32 noundef %0) local_unnamed_addr #0 {
  %.not7 = icmp slt i32 %0, 1
  br i1 %.not7, label %._crit_edge, label %.lr.ph.preheader

.lr.ph.preheader:                                 ; preds = %1
  %2 = shl nuw i32 %0, 1
  %3 = add nsw i32 %0, -1
  %4 = zext nneg i32 %3 to i33
  %5 = add nsw i32 %0, -2
  %6 = zext i32 %5 to i33
  %7 = mul i33 %4, %6
  %8 = lshr i33 %7, 1
  %9 = trunc i33 %8 to i32
  %10 = add i32 %2, %9
  %11 = add i32 %10, -1
  br label %._crit_edge

._crit_edge:                                      ; preds = %.lr.ph.preheader, %1
  %.06.lcssa = phi i32 [ 0, %1 ], [ %11, %.lr.ph.preheader ]
  ret i32 %.06.lcssa
}
```

Note those block names: `%.lr.ph.preheader`, `%._crit_edge`, `%.06.lcssa`. **`lr.ph` is short for "loop rotate, preheader", `_crit_edge` is "critical edge", and `lcssa` is "loop-closed SSA form".** The names the optimizer gives blocks leak which transformations it performed — see names like these and you know the loop went through `loop-rotate`.

**The loop is gone!** The entire summation has been replaced by the closed-form formula `n*(n+1)/2`.

**Note those `i33`s.** Why 33 bits rather than 32? Because the product of two 32-bit operands has to fit inside a single `mul` without overflowing. **In C you cannot declare a 33-bit integer, but IR can.** This is a direct demonstration that IR is more flexible than C — the optimizer can invent intermediate types of exactly the right width.

The teaching value of this experiment is that you can watch the complete evolution chain "code → memory operations → SSA → mathematical formula" with your own eyes, and every step can be verified separately.

---

## B.7 A misconception that must be cleared up

**"The output of `clang -O2`" ≠ "running `opt -O2` on the output of `clang -O0`".**

Measured:

```bash
clang-18 -S -emit-llvm -O0 abs_v.c -o abs_v.O0.ll
opt-18 -passes='default<O2>' -S abs_v.O0.ll -o -
```

**No optimization at all.** Because `optnone` is still there (see [B.2](#b2-why-running-opt-does-nothing-optnone)), the whole `default<O2>` pipeline ignores this function.

Remove `optnone` and try again:

```bash
sed 's/ optnone//' abs_v.O0.ll > abs_v.nooptnone.ll
opt-18 -passes='default<O2>' -S abs_v.nooptnone.ll -o -
```

```llvm
define dso_local i32 @abs_v(i32 noundef %0) local_unnamed_addr #0 {
  %.0 = tail call i32 @llvm.abs.i32(i32 %0, i1 true)
  ret i32 %.0
}
```

This time it worked, and the result matches what `clang -O2` generates directly (both become the `llvm.abs` intrinsic).

### The three layers of this misconception

1. **`optnone` silently disables the entire pipeline** — no error, no warning, nothing done.
2. **`clang -O2` is not just "front end + opt pipeline".** clang performs some optimizations already in the front end (constant folding, pattern matching) that are not in the `opt` pipeline.
3. **Order matters.** Some optimizations do not work well on `-O0`-style IR (inlining decisions, for instance), because they depend on the cleanup done by earlier passes.

**So: if you want to study optimization, start from `-O0` IR, remove `optnone` by hand, and then add passes step by step.** That is the most controllable workflow.

---

## B.8 Debugging the IR during optimization

To find out "which pass changed my code":

```bash
opt-18 -passes='default<O2>' -print-after-all -S in.ll -o /dev/null 2> trace.txt
```

`trace.txt` contains **the full IR after every pass**:

```
*** IR Dump After PromotePass on sum_to ***
define ...
*** IR Dump After InstCombinePass on sum_to ***
define ...
```

Note that the LLVM 18 format **includes the pass's class name** (`mem2reg`'s class name is `PromotePass`).

Related options:

| Option | Effect |
|---|---|
| `-print-after-all` | Print after every pass |
| `-print-before-all` | Print before every pass |
| `-print-changed` | Print **only when the IR actually changed** (far less output) |
| `-print-module-scope` | Always print the whole module instead of the current function |
| `-verify-each` | Run the verifier after every pass |

**`-print-changed` is especially useful**, because `-print-after-all` under `-O2` produces several megabytes of output while most passes change nothing.

Other commonly used tools:

| Tool | Purpose |
|---|---|
| `llvm-as-18` | `.ll` → `.bc`, **and verifies** |
| `llvm-dis-18` | `.bc` → `.ll` |
| `opt-18` | Run an optimization pipeline |
| `llc-18` | `.ll`/`.bc` → target assembly or object file |
| `lli-18` | Interpret and run `.bc` directly |
| `llvm-link-18` | Link multiple modules |
| `llvm-nm-18` | Inspect the symbol table |
| `opt-18 -passes=verify` | Verify IR on its own |

A complete workflow:

```bash
clang-18 -S -emit-llvm -O2 prog.c -o prog.ll   # C → IR
llc-18 prog.ll -o prog.s                       # IR -> assembly
llc-18 -filetype=obj prog.ll -o prog.o         # IR -> object file
lli-18 prog.ll                                 # run directly (needs main)
```

**A practical trick**: to find out "what assembly a given IR construct turns into", write a small piece of IR and hand it straight to `llc`:

```bash
$ cat > t.ll <<'EOF'
define i32 @f(i32 %a, i32 %b) {
  %r = mul i32 %a, %b
  ret i32 %r
}
EOF
$ llc-18 -O2 t.ll -o - | grep -v "^\s*\."
f:                                      # @f
	movl	%edi, %eax
	imull	%esi, %eax
	retq
```

The x86-64 System V convention puts the first argument in `%edi` and the second in `%esi`. `imull %esi, %eax` is a two-operand instruction (`%eax = %eax * %esi`), so the result has to be written back into one of the operands — that is why the backend has to move `a` into `%eax` first. It also explains why the operand order of `mul_add` from Chapter 2 of the main text looks "reversed" under `-O2`: **the instruction-selection stage is already taking `imul`'s encoding constraints into account.**

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Appendix A Differences from Common Claims](21-appendix-a-differences-from-common-claims.md) · [Next: Appendix C Compiler Implementation Notes →](23-appendix-c-compiler-implementation-notes.md)
