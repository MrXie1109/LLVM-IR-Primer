# Appendix D LLVM IR Instruction Quick Reference

## D.0 How to use it

This is a **lookup** set of tables, not a tutorial. You do not need to memorize any of it.

- Want to know "which instruction a particular C operation maps to" → see [D.1](#d1-lookup-by-task-c-operation-ir-instruction)
- Want to know "the complete syntax of an instruction" → see [D.2](#d2-complete-instruction-syntax)
- Want to know "which instructions a particular flag can be attached to" → see [D.3](#d3-flags-and-attributes-quick-reference)
- Want to know "what a particular comparison predicate means" → see [D.4](#d4-complete-comparison-predicate-tables)

Every entry has been verified on **LLVM 18.1.3**. The types are all illustrated with `i32`/`ptr`/`double`; in practice you can substitute any legal type.

---

## D.1 Lookup by task: C operation → IR instruction

### Integer arithmetic

| C | IR | Notes |
|---|---|---|
| `a + b` | `add i32 %a, %b` | clang adds `nsw` for signed |
| `a - b` | `sub i32 %a, %b` | Same as above |
| `a * b` | `mul i32 %a, %b` | Same as above |
| `-a` | `sub nsw i32 0, %a` | IR has no negation instruction |
| `a / b` (`int`) | `sdiv i32 %a, %b` | Division by zero is UB |
| `a / b` (`unsigned`) | `udiv i32 %a, %b` | |
| `a % b` (`int`) | `srem i32 %a, %b` | |
| `a % b` (`unsigned`) | `urem i32 %a, %b` | |

### Bitwise operations and shifts

| C | IR | Notes |
|---|---|---|
| `a & b` | `and i32 %a, %b` | |
| `a \| b` | `or i32 %a, %b` | |
| `a ^ b` | `xor i32 %a, %b` | |
| `~a` | `xor i32 %a, -1` | IR has no `not` instruction |
| `a << b` | `shl i32 %a, %b` | |
| `a >> b` (signed) | `ashr i32 %a, %b` | Sign-extends |
| `a >> b` (unsigned) | `lshr i32 %a, %b` | Zero-fills |

### Comparisons (all results are `i1`)

| C | IR |
|---|---|
| `a < b` (`int`) | `icmp slt i32 %a, %b` |
| `a <= b` (`int`) | `icmp sle i32 %a, %b` |
| `a > b` (`int`) | `icmp sgt i32 %a, %b` |
| `a >= b` (`int`) | `icmp sge i32 %a, %b` |
| `a < b` (`unsigned`) | `icmp ult i32 %a, %b` |
| `a == b` | `icmp eq i32 %a, %b` |
| `a != b` | `icmp ne i32 %a, %b` |
| `p == NULL` | `icmp eq ptr %p, null` |

### Floating point

| C | IR |
|---|---|
| `a + b` (`double`) | `fadd double %a, %b` |
| `a - b` | `fsub double %a, %b` |
| `a * b` | `fmul double %a, %b` |
| `a / b` | `fdiv double %a, %b` |
| `fmod(a,b)` | `frem double %a, %b` |
| `-a` | `fneg double %a` |
| `a < b` | `fcmp olt double %a, %b` |
| `a != b` | `fcmp une double %a, %b` |
| `a` is NaN | `fcmp uno double %a, %a` |

### Type conversions

| C | IR | Direction |
|---|---|---|
| `(long)x`, `x` is `int` | `sext i32 %x to i64` | Integer widening, keeps the sign |
| `(unsigned long)x` | `zext i32 %x to i64` | Integer widening, zero-fills |
| `(int)y`, `y` is `long` | `trunc i64 %y to i32` | Integer narrowing |
| `(char)x` | `trunc i32 %x to i8` | |
| `(_Bool)x` | `icmp ne i32 %x, 0` | Booleanization |
| `(double)x`, `x` is `int` | `sitofp i32 %x to double` | Signed integer → float |
| `(double)u`, `u` is `unsigned` | `uitofp i32 %u to double` | Unsigned integer → float |
| `(int)d`, `d` is `double` | `fptosi double %d to i32` | Float → signed integer |
| `(unsigned)d` | `fptoui double %d to i32` | Float → unsigned integer |
| `(double)f`, `f` is `float` | `fpext float %f to double` | Float widening |
| `(float)d` | `fptrunc double %d to float` | Float narrowing |
| `(uintptr_t)p` | `ptrtoint ptr %p to i64` | Pointer → integer |
| `(void*)x` | `inttoptr i64 %x to ptr` | Integer → pointer |
| `(int)x`, `x` is `unsigned` | **No instruction** | Both are `i32`, identity |

### Memory and addresses

| C | IR |
|---|---|
| `*p` | `load i32, ptr %p, align 4` |
| `*p = v` | `store i32 %v, ptr %p, align 4` |
| `p->field` | `getelementptr inbounds %struct.S, ptr %p, i32 0, i32 <field index>` |
| `a[i]` | `getelementptr inbounds i32, ptr %a, i64 %i` |
| `&g` (global) | Use `@g` directly (it is itself a pointer) |
| `&x` (local) | The `ptr` obtained from `alloca` |
| Local variable | `alloca i32, align 4` |
| VLA | `alloca i32, i32 %n, align 4` |

### Control flow

| C | IR |
|---|---|
| `return v;` | `ret i32 %v` |
| `return;` | `ret void` |
| Unconditional jump | `br label %target` |
| `if (c)` | `br i1 %cond, label %then, label %else` |
| `switch` | `switch i32 %x, label %default [ i32 0, label %c0 ... ]` |
| `c ? a : b` (no side effects) | `select i1 %c, i32 %a, i32 %b` |
| `c ? a : b` (branches) | `br` + `phi` |
| Value at a merge point | `phi i32 [ %v1, %b1 ], [ %v2, %b2 ]` |
| Unreachable | `unreachable` |
| Function call | `call i32 @f(i32 %a)` |
| Indirect call | `call i32 %fp(i32 %a)` |

---

## D.2 Complete instruction syntax

Below are the **complete syntaxes** by category. `<ty>` denotes a type, `<val>` denotes a value.

### Terminators (every basic block must have exactly one)

```llvm
ret void
ret <ty> <val>
br label %<label>
br i1 <cond>, label %<iftrue>, label %<iffalse>
switch <ty> <val>, label %<default> [ <ty> <c1>, label %<l1> ... ]
indirectbr ptr <addr>, [ label %<l1>, label %<l2> ... ]
unreachable
invoke <ty> @<fn>(<args>) to label %<normal> unwind label %<exception>
resume <ty> <val>
```

### Binary operations

```llvm
<op> <ty> <op1>, <op2>        ; general form

; integer
add   sub   mul   udiv   sdiv   urem   srem
shl   lshr  ashr  and    or     xor

; floating point
fadd  fsub  fmul  fdiv   frem
```

### Unary operations

```llvm
fneg <ty> <val>
```

### Comparisons

```llvm
icmp <pred> <ty> <op1>, <op2>
fcmp <pred> <ty> <op1>, <op2>
```

### Type conversions

```llvm
trunc  <ty1> <val> to <ty2>     ; integer narrowing
zext   <ty1> <val> to <ty2>     ; integer widening (fills with 0); may take nneg
sext   <ty1> <val> to <ty2>     ; integer widening (sign-extends)
fptrunc <ty1> <val> to <ty2>    ; float narrowing
fpext   <ty1> <val> to <ty2>    ; float widening
fptoui  <ty1> <val> to <ty2>    ; float -> unsigned integer
fptosi  <ty1> <val> to <ty2>    ; float -> signed integer
uitofp  <ty1> <val> to <ty2>    ; unsigned integer -> float
sitofp  <ty1> <val> to <ty2>    ; signed integer -> float
ptrtoint ptr <val> to <ty>      ; pointer -> integer
inttoptr <ty> <val> to ptr      ; integer -> pointer
bitcast <ty1> <val> to <ty2>    ; reinterpret, same width
addrspacecast ptr <val> to ptr addrspace(<n>)
```

### Memory

```llvm
alloca <ty>, align <n>
alloca <ty>, <ty> <count>, align <n>          ; dynamic size

load <ty>, ptr <ptr>, align <n>
load volatile <ty>, ptr <ptr>, align <n>
load atomic <ty>, ptr <ptr> <ordering>, align <n>

store <ty> <val>, ptr <ptr>, align <n>
store volatile <ty> <val>, ptr <ptr>, align <n>
store atomic <ty> <val>, ptr <ptr> <ordering>, align <n>

getelementptr [inbounds] <ty>, ptr <ptr>, <ty> <idx> [, <ty> <idx> ...]

fence <ordering>
cmpxchg [weak|strong] ptr <ptr>, <ty> <cmp>, <ty> <new> <success_ordering> <failure_ordering>
atomicrmw <op> ptr <ptr>, <ty> <val> <ordering>
```

### Other

```llvm
phi <ty> [ <val1>, %<label1> ], [ <val2>, %<label2> ], ...
select i1 <cond>, <ty> <val1>, <ty> <val2>
call [fast-math flags] <ty> @<fn>(<args>)
call <ty> <fnptr>(<args>)                      ; indirect call
tail call <ty> @<fn>(<args>)
va_arg <ty>, ptr <ap>
landingpad <ty> cleanup | catch <ty> <val>
freeze <ty> <val>
extractvalue <agg> <val>, <idx> [, <idx> ...]
insertvalue <agg> <val>, <ty> <elt>, <idx> [, <idx> ...]
extractelement <vec> <val>, <ty> <idx>
insertelement <vec> <val>, <ty> <elt>, <ty> <idx>
shufflevector <vec> <v1>, <vec> <v2>, <vec> <mask>
```

---

## D.3 Flags and attributes quick reference

### Which instructions support which flags

| Flag | Meaning | Applicable to |
|---|---|---|
| `nsw` | Signed overflow → poison | `add` `sub` `mul` `shl` |
| `nuw` | Unsigned overflow → poison | `add` `sub` `mul` `shl` |
| `exact` | Division/shift has no remainder, otherwise poison | `udiv` `sdiv` `lshr` `ashr` |
| `nneg` | The source value is non-negative | `zext` |
| `inbounds` | The address arithmetic stays within the object | `getelementptr` |
| `disjoint` | The set bits of the operands do not overlap | **`or` only** (`and`/`xor` report `expected type`) |

**Note that `trunc` supports no flags at all** (see [Appendix A.1.3](21-appendix-a-differences-from-common-claims.md#a13-trunc-accepts-no-flags-at-all)).

### Floating-point fast-math flags

| Flag | Meaning |
|---|---|
| `nnan` | Assume no NaNs |
| `ninf` | Assume no infinities |
| `nsz` | Ignore the difference between ±0 |
| `arcp` | Allow division to become multiplication by a reciprocal |
| `contract` | Allow merging into an FMA |
| `afn` | Allow approximate functions |
| `reassoc` | Allow reassociation (**breaks associativity**) |
| `fast` | All of the above (the most aggressive) |

Applicable to `fadd` `fsub` `fmul` `fdiv` `frem` `fneg` `fcmp` `call` (for calls returning floating point).

### Common function attributes

| Attribute | Meaning |
|---|---|
| `noinline` / `alwaysinline` / `inlinehint` | Inlining control |
| `optnone` | **Forbids all optimization** (used by `-O0`; silently disables every pass) |
| `optsize` / `minsize` | Optimize for size |
| `noreturn` | Never returns |
| `nounwind` | Does not throw exceptions |
| `willreturn` | Will definitely return |
| `mustprogress` | Loops must finish within a finite number of steps |
| `readnone` / `readonly` / `writeonly` | Memory access behaviour (old style) |
| `memory(none)` / `memory(read)` / `memory(write)` | Memory access behaviour (new style, recommended) |
| `norecurse` | Does not recurse directly |
| `nofree` / `nosync` | Does not free memory / has no synchronization operations |
| `cold` / `hot` | Execution-frequency hints |
| `uwtable` | Generate stack unwind tables |
| `ssp` / `sspstrong` | Stack protection |

### Common parameter and return-value attributes

| Attribute | Position | Meaning |
|---|---|---|
| `noundef` | Parameter/return value | Will not be `undef`/`poison` |
| `zeroext` / `signext` | Parameter/return value | Zero-extend / sign-extend to register width |
| `noalias` | Parameter/return value | Does not alias other pointers (C's `restrict`) |
| `nocapture` | Parameter | Will not be stored anywhere else |
| `readonly` / `writeonly` / `readnone` | Parameter | Not written / not read / neither read nor written through it |
| `dereferenceable(N)` | Parameter | Points to at least N bytes of valid memory |
| `dereferenceable_or_null(N)` | Parameter | Either null, or dereferenceable for N bytes |
| `align N` | Parameter | The pointer is aligned to N |
| `returned` | Parameter | The return value is this parameter |
| `byval` / `byref` | Parameter | Pass an aggregate by value / by reference |
| `sret` | Parameter | The address to store a struct return value |

### Linkage

| Attribute | Corresponding C | Notes |
|---|---|---|
| (none) | Ordinary global symbol | Externally visible |
| `private` | — | This module only, not in the symbol table |
| `internal` | `static` | This module only, in the symbol table (easier to debug) |
| `available_externally` | — | For inlining only, no code generated |
| `linkonce` / `linkonce_odr` | Template/inline functions | Can be defined repeatedly, one copy is kept |
| `weak` / `weak_odr` | `__attribute__((weak))` | Can be overridden by a stronger definition |
| `common` | Tentative definition | Can be merged with other `common` symbols |
| `appending` | — | Only for `llvm.global_ctors` and the like |
| `extern_weak` | `extern` + weak | Weak external reference |

### Visibility (written **before** `global`/`constant`)

```llvm
@a = default global i32 1      ; may be omitted
@b = hidden global i32 2
@c = protected global i32 3
```

### Calling conventions

| Keyword | Use |
|---|---|
| (omitted, i.e. `ccc`) | The C calling convention, the platform default |
| `fastcc` | LLVM's internal convention, **cannot be called across modules** |
| `coldcc` | Rarely executed paths |
| `cc <n>` | A platform-specific convention (e.g. `cc 10` is GHC) |

---

## D.4 Complete comparison predicate tables

### `icmp` predicates (10)

| Predicate | Meaning | Signed or unsigned |
|---|---|---|
| `eq` | Equal | Neither |
| `ne` | Not equal | Neither |
| `ugt` | Greater than | Unsigned |
| `uge` | Greater than or equal | Unsigned |
| `ult` | Less than | Unsigned |
| `ule` | Less than or equal | Unsigned |
| `sgt` | Greater than | Signed |
| `sge` | Greater than or equal | Signed |
| `slt` | Less than | Signed |
| `sle` | Less than or equal | Signed |

**`eq`/`ne` have no `s`/`u` variants** — equality is bitwise equality.

### `fcmp` predicates (16)

`o` = **o**rdered: meaningful only when **neither operand is NaN**.
`u` = **u**nordered: **true** when either operand is NaN.

| Predicate | Meaning |
|---|---|
| `false` | Always false |
| `oeq` | Ordered and equal |
| `ogt` | Ordered and greater than |
| `oge` | Ordered and greater than or equal |
| `olt` | Ordered and less than |
| `ole` | Ordered and less than or equal |
| `one` | Ordered and not equal |
| `ord` | Ordered (neither is NaN) |
| `ueq` | Unordered or equal |
| `ugt` | Unordered or greater than |
| `uge` | Unordered or greater than or equal |
| `ult` | Unordered or less than |
| `ule` | Unordered or less than or equal |
| `une` | Unordered or not equal |
| `uno` | Unordered (at least one is NaN) |
| `true` | Always true |

### Which one a C floating-point comparison maps to

| C | Predicate | Why |
|---|---|---|
| `a < b` | `olt` | With NaN involved C requires false = "ordered and less than" |
| `a <= b` | `ole` | Same as above |
| `a > b` | `ogt` | Same as above |
| `a >= b` | `oge` | Same as above |
| `a == b` | `oeq` | Returns false when NaN is involved |
| **`a != b`** | **`une`** | Returns **true** when NaN is involved (NaN != NaN is true) |

**The last row is a classic trap**: `!=` corresponds to `une` (unordered **or** not equal), not `one`.

### Signedness

| Predicate | Meaning |
|---|---|
| `slt` | Signed less than |
| `ult` | Unsigned less than |
| `eq` | Equal |

`-1` as an unsigned number is 4294967295, so `(unsigned)-1 < 1` is false while `-1 < 1` is true — the same `i32`, different predicates. **Signedness is not in the type; it is in the predicate.**

---

## D.5 Intrinsics quick reference

Intrinsic names start with `llvm.` and the backend generates code for them directly.

| Category | Examples |
|---|---|
| Memory | `llvm.memcpy.p0.p0.i64`, `llvm.memmove`, `llvm.memset` |
| Bit manipulation | `llvm.ctpop`, `llvm.ctlz`, `llvm.cttz`, `llvm.bitreverse`, `llvm.bswap` |
| Integer math | `llvm.abs`, `llvm.smax`, `llvm.smin`, `llvm.umax`, `llvm.umin` |
| Floating-point math | `llvm.fabs`, `llvm.sqrt`, `llvm.floor`, `llvm.ceil`, `llvm.round`, `llvm.fma` |
| Saturating arithmetic | `llvm.sadd.sat`, `llvm.uadd.sat`, `llvm.ssub.sat`, `llvm.usub.sat` |
| Overflow checking | `llvm.sadd.with.overflow`, `llvm.umul.with.overflow`, and so on |
| Debugging/traps | `llvm.trap`, `llvm.debugtrap`, `llvm.dbg.value` |
| Varargs | `llvm.va_start`, `llvm.va_end`, `llvm.va_copy` |
| Stack/frame | `llvm.frameaddress`, `llvm.returnaddress`, `llvm.stacksave`, `llvm.stackrestore` |
| Vectors | `llvm.vector.reduce.add`, `llvm.masked.load`, `llvm.masked.store` |

**The types are encoded in the name**: `llvm.ctpop.i32` operates on `i32`; `llvm.memcpy.p0.p0.i64` means "pointer to address space 0, pointer to address space 0, `i64` length". This is because LLVM function names do not support overloading, so a naming convention distinguishes them.

Overflow-checking intrinsics return a **struct**, which is where IR is more powerful than C:

```llvm
declare { i32, i1 } @llvm.sadd.with.overflow.i32(i32, i32)

%r    = call { i32, i1 } @llvm.sadd.with.overflow.i32(i32 %a, i32 %b)
%sum  = extractvalue { i32, i1 } %r, 0
%ovf  = extractvalue { i32, i1 } %r, 1
```

C's `__builtin_add_overflow` compiles to exactly this.

---

## D.6 Types quick reference

| Type | Spelling | Notes |
|---|---|---|
| Integer | `i1` `i8` `i16` `i32` `i64` `i128` `iN` | **Any bit width** |
| Floating point | `half` `float` `double` `fp128` `x86_fp80` `ppc_fp128` | `half` is 16 bits |
| Pointer | `ptr` | The only one in LLVM 18 |
| Array | `[10 x i32]` | |
| Struct | `{ i32, i8 }` | Has padding |
| Packed struct | `<{ i32, i8 }>` | No padding |
| Vector | `<4 x i32>` | SIMD |
| Label | `label` | Only usable with `br`/`switch` |
| Void | `void` | Only usable as a return type |

### C types → IR types

| C | IR | Parameter attribute |
|---|---|---|
| `char` / `signed char` | `i8` | `signext` |
| `unsigned char` | `i8` | `zeroext` |
| `short` | `i16` | `signext` |
| `unsigned short` | `i16` | `zeroext` |
| `int` | `i32` | — |
| `unsigned` | `i32` | — |
| `long` / `long long` (Linux x86-64) | `i64` | — |
| `_Bool` | `i1` | `zeroext` |
| `float` | `float` | — |
| `double` | `double` | — |
| `long double` (x86-64) | `x86_fp80` | Target-dependent |
| Any pointer | `ptr` | — |
| Array as a parameter | `ptr` | Decays to a pointer |

### Special values

| Spelling | Meaning |
|---|---|
| `null` | The zero value of a pointer |
| `undef` | "Any value at all", may differ on each read |
| `poison` | A poisoned value, contaminates downstream; UB if it affects observable behaviour |
| `zeroinitializer` | All zeros, usable with any type |
| `true` / `false` | 1 / 0 for `i1` |

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Appendix C Compiler Implementation Notes](23-appendix-c-compiler-implementation-notes.md)
