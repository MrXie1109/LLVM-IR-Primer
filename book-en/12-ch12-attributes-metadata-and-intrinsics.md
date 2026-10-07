# Chapter 12 Attributes, Metadata and Intrinsics

## 12.1 Referring back: that long dense `attributes` line from Chapter 2

In Chapter 2, when we first saw the complete output for `mul_add`, there was a line that was marked at the time as "irrelevant to teaching, omitted":

```llvm
attributes #0 = { noinline nounwind optnone uwtable "frame-pointer"="all" "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
```

And these at the end of the file:

```llvm
!llvm.module.flags = !{!0, !1, !2, !3, !4}
!llvm.ident = !{!5}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 8, !"PIC Level", i32 2}
...
```

In Chapter 3 we saw `nsw` again, in Chapter 6 `inbounds`, and in Chapter 7 `noreturn`, `returned`, `nocapture`.

**None of these things is decoration.** They are the **promises** and **hints** the front end gives the optimizer, and they directly determine what the optimizer can do. This chapter systematizes them.

## 12.2 The three carriers of "extra information"

There are three different places in IR where extra information can go, and they serve different purposes:

| Carrier | Syntax | Scope | Examples |
|---|---|---|---|
| **Instruction flags** | follow the instruction name | a single instruction | `add nsw`, `getelementptr inbounds` |
| **Attributes** | `#0` or written directly | function / parameter / return value / call site | `noinline`, `noundef`, `readonly` |
| **Metadata** | starts with `!` | module / function / instruction | `!dbg`, `!tbaa`, `!llvm.module.flags` |

**The key differences**:

- **Instruction flags** affect the semantics of that one instruction (`nsw` changes the definition of overflow);
- **Attributes** are "facts about this function/parameter" that the optimizer may rely on;
- **Metadata** is "annotation", and **by default does not affect correctness** — dropping metadata will not make a program wrong, it will only make optimization worse (except debug information, which affects debuggability).

## 12.3 Function attributes

### Common function attributes

```llvm
define i32 @f(i32 %x) #0 {
  ret i32 %x
}
attributes #0 = { noinline nounwind }
```

| Attribute | Meaning |
|---|---|
| `noinline` | forbid inlining |
| `alwaysinline` | force inlining |
| `inlinehint` | suggest inlining |
| `optnone` | **forbid all optimization** (used by `-O0`) |
| `optsize` | optimize for size |
| `optforfuzzing` | optimize for fuzzing (preserve more behaviour) |
| `noreturn` | never returns |
| `nounwind` | will not throw exceptions |
| `willreturn` | will definitely return (does not enter an infinite loop) |
| `norecurse` | this function does not call itself directly recursively |
| `nofree` | does not free memory |
| `nosync` | does not synchronize (no atomics or memory fences) |
| `cold` | rarely executed (put it on a cold path) |
| `hot` | frequently executed |
| `mustprogress` | loops must terminate within a finite number of steps (C11 forward progress) |
| `uwtable` | generate stack unwinding tables |
| `ssp` / `sspstrong` | stack protection |
| `readnone` | neither reads nor writes memory (a pure function) |
| `readonly` | only reads memory, does not write |
| `writeonly` | only writes memory |
| `argmemonly` | accesses memory only through its arguments |
| `inaccessiblememonly` | accesses only inaccessible memory |
| `memory(...)` | a fine-grained description of memory behaviour |

### `memory(...)`: LLVM's latest generation of memory attributes

Since LLVM 16, the older attributes `readnone`/`readonly`/`argmemonly` have gradually been replaced by the unified `memory(...)`:

```llvm
attributes #0 = { memory(none) }                      ; accesses no memory at all
attributes #1 = { memory(read) }                      ; read only
attributes #2 = { memory(write) }                     ; write only
attributes #3 = { memory(readwrite) }                 ; read and write
attributes #4 = { memory(argmem: read) }              ; reads only the memory pointed to by arguments
attributes #5 = { memory(inaccessiblemem: write) }    ; writes only inaccessible memory
attributes #6 = { memory(argmem: readwrite, inaccessiblemem: readwrite) }
```

Measured: the `noreturn` function from Chapter 7:

```llvm
; Function Attrs: noreturn nounwind memory(inaccessiblemem: write) uwtable
define dso_local void @die() local_unnamed_addr #1 {
  tail call void @llvm.trap()
  unreachable
}
```

`memory(inaccessiblemem: write)` means "this function only writes memory that cannot be accessed by normal means". `llvm.trap()` triggers a trap, which may be recorded by the debugger into some inaccessible memory region, so clang describes it this way.

### Attribute groups

```llvm
attributes #0 = { noinline nounwind }
attributes #1 = { alwaysinline nounwind }
```

Attribute groups appear at the end of the file and are referred to by functions via `#0`. This is for **deduplication** — when several functions share attributes, they are written only once.

You can also write attributes **inline** directly on a function:

```llvm
define i32 @g(i32 %x) noinline nounwind {
  ret i32 %x
}
```

The two forms are equivalent. clang always uses attribute groups.

## 12.4 Parameter and return value attributes

These are what you most often see when reading clang output:

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
```

| Attribute | Position | Meaning |
|---|---|---|
| `noundef` | parameter/return value | will not be `undef` or `poison` |
| `zeroext` | parameter/return value | zero-extended to the register width |
| `signext` | parameter/return value | sign-extended to the register width |
| `noalias` | parameter/return value | does not alias any other pointer |
| `nocapture` | parameter | will not be stored anywhere else |
| `readonly` | parameter | the function does not write memory through it |
| `writeonly` | parameter | the function does not read memory through it |
| `readnone` | parameter | the function neither reads nor writes through it |
| `dereferenceable(N)` | parameter | points to at least N bytes of valid memory |
| `dereferenceable_or_null(N)` | parameter | either null, or N bytes can be dereferenced |
| `align N` | parameter | the pointer is aligned to N |
| `byval` / `byref` | parameter | pass an aggregate by value / by reference |
| `sret` | parameter | the address of the struct return value |
| `returned` | parameter | the return value is this parameter |

### Why is `noundef` everywhere?

Since Chapter 2, every parameter in clang's output carries `noundef`. The reason:

In C **passing an uninitialized value is UB** (for most types). Since the programmer guarantees it will not happen, clang can annotate "this parameter will not be `undef`".

**This gives the optimizer a great deal of power.** For example:

```llvm
%cond = icmp eq i32 %x, %x    ; if %x might be undef, the result is indeterminate
```

With `noundef`, the optimizer knows `%x` is a determinate value, so `%x == %x` is always true (except for floating point NaN). Without `noundef`, `undef != undef` is possible, and this fold would be illegal.

### `returned`

```llvm
define dso_local noundef i32 @sitofp_it(i32 noundef returned %0) local_unnamed_addr #0 {
```

In Chapter 7 we saw that `noinline_f` also carries `returned`.

`returned` means "the return value is `%0`". With it, the caller can save a copy:

```llvm
; with returned:
%r = call i32 @f(i32 %x)
; %x can be used directly in place of %r

; without returned:
%r = call i32 @f(i32 %x)
; the return value really has to be received
```

**Note that `returned` is inferred by clang**; when you write C you do not need to (and cannot) specify it.

### `noalias` and C's `restrict`

```c
void add_arrays(int *restrict dst, const int *restrict a, int n) {
    for (int i = 0; i < n; i++) dst[i] += a[i];
}
```

```llvm
define dso_local void @add_arrays(ptr noalias nocapture noundef %0, ptr noalias nocapture noundef readonly %1, i32 noundef %2) local_unnamed_addr #0 {
```

`restrict` → `noalias`. It tells the optimizer "these two pointers do not point to the same memory", so vectorization is safe.

**Without `noalias`**, the optimizer must assume `dst` and `a` may overlap, so it cannot reorder the loop. **This is the most valuable use of `restrict` in C.**

## 12.5 Metadata

### Module-level metadata

You can see this at the end of every clang output file:

```llvm
!llvm.module.flags = !{!0, !1, !2, !3, !4}
!llvm.ident = !{!5}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 8, !"PIC Level", i32 2}
!2 = !{i32 7, !"PIE Level", i32 2}
!3 = !{i32 7, !"uwtable", i32 2}
!4 = !{i32 7, !"frame-pointer", i32 2}
!5 = !{!"Ubuntu clang version 18.1.3 (1ubuntu1)"}
```

Each entry of `!llvm.module.flags` has the form `!{behaviour, "name", value}`, where the **behaviour** is:

| Value | Meaning |
|---|---|
| 1 | **Error**: if this flag is not understood, report an error |
| 2 | **Warning**: if not understood, warn |
| 3 | **Require**: if a tool does not implement it, refuse to process |
| 4 | **Override**: a later occurrence of the same flag overrides an earlier one |
| 5 | **Append**: append to the existing list of values |
| 6 | **AppendUnique**: append and deduplicate (both values must be metadata nodes) |
| 7 | **Max**: take the maximum value |
| 8 | **Min**: take the minimum value |

(The legal values are only 1–8, and there is **no** "Modulo" behaviour — some sources get this wrong. The full comparison and its sources are in [Appendix A.3.1](21-appendix-a-differences-from-common-claims.md#a31-the-behaviour-values-of-module-flags).)

What we see in the measurements:

- `!0 = !{i32 1, !"wchar_size", i32 4}` — behaviour 1 (Error), `wchar_t` is 4 bytes;
- `!1 = !{i32 8, !"PIC Level", i32 2}` — behaviour 8 (Min), the position-independent code level is 2;
- `!4 = !{i32 7, !"frame-pointer", i32 2}` — behaviour 7 (Max), the frame pointer mode is 2 (`all`).

**The point of these flags is consistency checking across the toolchain.** If two modules disagree about `wchar_size`, the link fails with an error instead of producing a subtle mistake.

### Debug metadata

With `-g` added, a large amount of debug information appears:

```llvm
!0 = distinct !DICompileUnit(language: DW_LANG_C11, file: !1, producer: "Ubuntu clang version 18.1.3 (1ubuntu1)", isOptimized: true, runtimeVersion: 0, emissionKind: FullDebug, splitDebugInlining: false, nameTableKind: None)
!10 = distinct !DISubprogram(name: "add", scope: !1, file: !1, line: 1, type: !11, scopeLine: 1, flags: DIFlagPrototyped | DIFlagAllCallsDescribed, spFlags: DISPFlagDefinition | DISPFlagOptimized, unit: !0, retainedNodes: !14)
!13 = !DIBasicType(name: "int", size: 32, encoding: DW_ATE_signed)
!15 = !DILocalVariable(name: "a", arg: 1, scope: !10, file: !1, line: 1, type: !13)
```

The `DI*` prefix stands for **D**ebug **I**nformation. This metadata is ultimately translated into DWARF debug information, so that gdb can show variable names and types.

**Note `!DIBasicType(name: "int", size: 32, encoding: DW_ATE_signed)`** — here the C name `int` and its **signedness** are preserved! This is exactly the compensation for what Chapter 3 said about "signedness is not in the IR type": it is lost in the type system and restored in the debug metadata.

Instructions, in turn, carry `!dbg`:

```llvm
%3 = add nsw i32 %1, %2, !dbg !17
```

### `!tbaa`: alias analysis hints

Seen in Chapter 4:

```llvm
%4 = load i32, ptr %0, align 4, !tbaa !5
```

`tbaa` = **T**ype-**B**ased **A**lias **A**nalysis. It tells the optimizer "what type this access goes through", so the optimizer can infer that "an `int` access will not alias a `float` access".

```llvm
!5 = !{!"int", !6, i64 0}
!6 = !{!"omnipotent char", !7, i64 0}
```

This is the IR expression of C's **strict aliasing** rule. It lets the optimizer do more reordering, at the price of making "accessing the same memory through pointers of different types" UB.

### Loop metadata

Seen in Chapter 5:

```llvm
br label %5, !llvm.loop !6
```

```llvm
!6 = distinct !{!6, !7}
!7 = !{!"llvm.loop.mustprogress"}
```

`!llvm.loop` attaches information about a loop (such as "this loop has the mustprogress guarantee") to the back edge. The optimizer uses it to decide whether loop transformations are allowed.

## 12.6 Intrinsics

The names of intrinsics all start with `llvm.`. **Their function bodies are not defined in IR; the backend generates the code directly.**

### Common categories of intrinsics

| Category | Examples |
|---|---|
| Memory | `llvm.memcpy`, `llvm.memmove`, `llvm.memset` |
| Bit manipulation | `llvm.ctpop`, `llvm.ctlz`, `llvm.cttz`, `llvm.bitreverse`, `llvm.bswap` |
| Math | `llvm.abs`, `llvm.smax`, `llvm.smin`, `llvm.umax`, `llvm.umin`, `llvm.fabs`, `llvm.sqrt` |
| Saturating arithmetic | `llvm.sadd.sat`, `llvm.uadd.sat`, `llvm.ssub.sat` |
| Overflow checking | `llvm.sadd.with.overflow`, `llvm.umul.with.overflow` |
| Floating point environment | `llvm.fma`, `llvm.floor`, `llvm.ceil`, `llvm.round` |
| Traps/debugging | `llvm.trap`, `llvm.debugtrap`, `llvm.dbg.value` |
| Varargs | `llvm.va_start`, `llvm.va_end`, `llvm.va_copy` |
| Stack/frame | `llvm.frameaddress`, `llvm.returnaddress`, `llvm.stacksave`, `llvm.stackrestore` |
| Coroutines | `llvm.coro.*` |
| Vectors | `llvm.vector.reduce.add`, `llvm.masked.load` |

### Measured: calling and running intrinsics

```llvm
declare i32 @llvm.ctpop.i32(i32)
declare i32 @llvm.smax.i32(i32, i32)

define i32 @ctpop_test(i32 %x) {
  %p = call i32 @llvm.ctpop.i32(i32 %x)
  ret i32 %p
}
define i32 @smax_test(i32 %a, i32 %b) {
  %m = call i32 @llvm.smax.i32(i32 %a, i32 %b)
  ret i32 %m
}
```

Testing with a C driver:

```c
#include <stdio.h>
int ctpop_test(int);
int smax_test(int,int);
int main(void){
  printf("ctpop(255)=%d smax(3,9)=%d\n", ctpop_test(255), smax_test(3,9));
  return 0;
}
```

```bash
$ llvm-as-18 intr2.ll -o intr2.bc
$ clang-18 -w intr_main.c intr2.bc -o intrtest && ./intrtest
ctpop(255)=8 smax(3,9)=9
```

**`llvm.ctpop.i32(255) = 8`** — it counts 8 ones in the binary representation of 255. The backend compiles it into a single `popcnt` instruction (if the CPU supports it) or a stretch of bit-twiddling code.

### Naming rules: type suffixes

An intrinsic's types are encoded in its name:

- `llvm.ctpop.i32` — operates on `i32`;
- `llvm.memcpy.p0.p0.i64` — a pointer to address space 0, a pointer to address space 0, and an `i64` length;
- `llvm.smax.i32` — the `i32` version.

**Why encode them in the name?** Because intrinsics need **overloading**, and LLVM's function names do not support overloading on argument types. So a naming convention works around it: `llvm.ctpop.i8` and `llvm.ctpop.i32` are two different functions.

### Overflow-checking intrinsics

This group is particularly interesting, because it returns a **struct**:

```llvm
declare { i32, i1 } @llvm.sadd.with.overflow.i32(i32, i32)

define i32 @safe_add(i32 %a, i32 %b) {
  %r = call { i32, i1 } @llvm.sadd.with.overflow.i32(i32 %a, i32 %b)
  %sum = extractvalue { i32, i1 } %r, 0
  %ovf = extractvalue { i32, i1 } %r, 1
  br i1 %ovf, label %overflow, label %ok
overflow:
  ret i32 0
ok:
  ret i32 %sum
}
```

`{ i32, i1 }` — the first field is the sum, the second is "whether it overflowed". This instruction corresponds directly to the CPU's overflow flag; `__builtin_add_overflow` compiles to it.

**This is an example of IR being "more powerful than C"**: C cannot obtain the result and the overflow flag from a single operation, but IR can.

## 12.7 Exercises

**Exercise 12.1** Generate the complete output for `mul_add` from Chapter 2 (omitting nothing), look up every attribute in `attributes #0`, and write down its meaning.

**Exercise 12.2** Compare the attribute groups for `mul_add` under `-O0` and `-O2`. Which attributes disappear? Why does `optnone` appear only under `-O0`?

**Exercise 12.3** Generate the IR with and without `-g` and compare the changes to `!llvm.module.flags`.

**Exercise 12.4** Hand-write a `.ll` file that uses `llvm.sadd.with.overflow.i32` to implement an addition that "returns 0 on overflow". Test it with a C driver and verify that the overflow detection is correct (try `INT_MAX + 1`).

**Exercise 12.5** Compile the following code and find the `noalias`:

```c
void copy(int *restrict dst, const int *restrict src, int n) {
    for (int i = 0; i < n; i++) dst[i] = src[i];
}
```

Then remove `restrict`, recompile, and observe how the IR differs.

**Exercise 12.6 (thought question)** Why can metadata be "lost without affecting correctness", whereas instruction flags (`nsw`) cannot be dropped?

## 12.8 Summary

- Three carriers of extra information: **instruction flags** (affect the semantics of a single instruction), **attributes** (facts about functions/parameters), **metadata** (annotation, does not affect correctness).
- Attribute group `#0` is used for deduplication; `optnone` is the key attribute of `-O0`.
- `memory(...)` is the new generation of memory behaviour descriptions and is replacing `readnone`/`readonly`/`argmemonly`.
- `noundef` comes from "passing an uninitialized value in C is UB" and gives the optimizer a great deal of power.
- Debug metadata preserves C's type names and signedness — compensating for the information the IR type system loses.
- `!tbaa` expresses the strict aliasing rule.
- Intrinsics start with `llvm.`, encode their types in the name, and have their code generated directly by the backend.
- `llvm.*.with.overflow` returns `{ result, overflow flag }`, a demonstration of IR's capabilities.

Next chapter we cover the optimization pipeline and see how `opt` puts this information to use.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 11 The Instruction Reference](11-ch11-instruction-reference.md) · [Next: Chapter 13 The Optimization Pipeline and `opt` →](13-ch13-the-optimization-pipeline-and-opt.md)
