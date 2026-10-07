# Appendix A Differences from Common Claims

## A.0 Who this appendix is for

Anything in the main text along the lines of "this widely repeated claim is actually wrong" or "this syntax detail is easy to get wrong" has been collected into this appendix.

**Why not leave it in the main text?** Because for someone learning LLVM IR for the first time, all of that is noise — you have not yet built the correct intuition, and committing "which spelling is wrong" to memory first only divides your attention. The main text teaches only the **correct, sufficient** set.

**So when should you read this appendix?** Three situations:

1. You followed some tutorial or blog and wrote a `.ll`, and `llvm-as` reported an error you do not understand;
2. You noticed that your output disagrees with this book (or with other material) and want to know who is right;
3. You can already read and write IR fluently and want to see which details are traps.

Every entry below gives the **actual command and the real output**. The environment is **LLVM 18.1.3**.

> **One general piece of advice**: both the main text of this book and this appendix can go stale (LLVM ships a major version every six months). **When there is a disagreement, run the command first, then read the documentation.** This is not a pleasantry — most of the entries in this appendix were originally discovered precisely because "what the book said" and "what the terminal said" did not agree.

---

## A.1 The syntax most easily written wrong in a hand-written `.ll`

This is the most important section. **If you read only one section of the appendix, read this one.** Because every entry below is of the form "write it the intuitive way and it errors out."

### A.1.1 Integer constants have no bare hexadecimal, and no binary either

**The intuitive spelling (wrong):**

```llvm
i32 0x2A          ; ← rejected
i32 0b101010      ; ← rejected
```

**Actual test:**

```bash
$ for lit in 42 -1 0x2A 0b101010 052 u0x2A s0x2A; do
    printf 'define i32 @f() {\n  %%a = add i32 %s, 1\n  ret i32 %%a\n}\n' "$lit" > t.ll
    printf "%-10s => " "$lit"
    llvm-as-18 t.ll -o /dev/null 2>/dev/null && echo ACCEPTED || llvm-as-18 t.ll -o /dev/null 2>&1 | head -1 | sed 's/.*error: //'
  done
42         => ACCEPTED
-1         => ACCEPTED
0x2A       => floating point constant invalid for type
0b101010   => expected ',' in arithmetic operation
052        => ACCEPTED
u0x2A      => ACCEPTED
s0x2A      => ACCEPTED
```

**The correct spelling:**

```llvm
i32 42            ; decimal
i32 -1            ; negative
i32 052           ; octal (leading 0, as in C)
u0x2A             ; hex requires a u (unsigned) or s (signed) prefix
s0x2A             ; signed hex
```

**Why does the error for `0x2A` mention "floating point"?** Because in LLVM syntax, `0x...` is the **hexadecimal bit pattern of a floating-point number** (for example, `double 0x4014000000000000` means 1.0). The parser sees `0x2A`, parses it as a floating-point value, then discovers that the type is `i32`, and so reports `floating point constant invalid for type`.

**This error is extremely misleading** — it makes you think it is a type problem, when in fact you wrote a literal that does not belong to integer syntax. Remember `u0x`/`s0x`.

**There is no binary literal in LLVM IR.** Write binary constants in decimal or as `u0x` hexadecimal.

### A.1.2 A global variable's visibility is a prefix, not a comma attribute

**The intuitive spelling (wrong):**

```llvm
@v = global i32 1, visibility protected     ; ← rejected
```

**Actual test:**

```bash
$ llvm-as-18 v.ll
llvm-as-18: v.ll:1:20: error: unknown global variable property!
@v = global i32 1, visibility protected
                   ^
```

**The correct spelling:**

```llvm
@v = protected global i32 1
@h = hidden global i32 2
```

**The rule**: `hidden` / `protected` go **before** `global` / `constant`, in the same position as the linkage values `private`, `internal`, and `external`. Things like `, align 4` and `, section ".x"` are what go after the comma.

clang's output confirms this:

```c
__attribute__((visibility("hidden"))) int hg = 1;
__attribute__((visibility("protected"))) int pg = 2;
```

```llvm
@hg = hidden global i32 1, align 4
@pg = protected global i32 2, align 4
```

### A.1.3 `trunc` accepts no flags at all

**The intuitive spelling (wrong):**

```llvm
%r = trunc nsw i32 %x to i8      ; ← rejected
%r = trunc nuw i32 %x to i8      ; ← rejected
%r = trunc exact i32 %x to i8    ; ← rejected
```

**Actual test:**

```bash
$ llvm-as-18 tr.ll
llvm-as-18: tr.ll:2:14: error: expected type
  %r = trunc nsw i32 %x to i8
             ^
```

The error is `expected type` — right after `trunc` the parser **expects a type directly**, and has no intention of accepting a flag.

**The only instructions that support `nsw`/`nuw` are `add`, `sub`, `mul`, and `shl`** (see Chapter 11 of the main text). `zext` has a separate `nneg` flag (meaning the source value is non-negative).

### A.1.4 `atomicrmw` has no `smax`/`smin`

**The intuitive spelling (wrong):**

```llvm
%r = atomicrmw smax ptr %p, i32 1 seq_cst    ; ← rejected
```

**Actual test:**

```bash
$ for op in xchg add sub and nand or xor max min umax umin smax smin uinc_wrap udec_wrap; do ... done
xchg         => OK
add          => OK
sub          => OK
and          => OK
nand         => OK
or           => OK
xor          => OK
max          => OK
min          => OK
umax         => OK
umin         => OK
smax         => expected binary operation in atomicrmw
smin         => expected binary operation in atomicrmw
uinc_wrap    => OK
udec_wrap    => OK
```

**The rule**: `max` / `min` **are themselves the signed versions**; the unsigned versions are `umax` / `umin`. `smax` / `smin` **do not exist**.

(Note that this differs from the naming rule for `icmp` — there it really is `slt`/`ult`. Historical baggage left `atomicrmw` without an `s` prefix.)

### A.1.5 Named values and numbered values **can** be mixed

**The common claim (wrong):** "Inside one function, named values `%name` and numbered values `%0` cannot be mixed."

**Actual test:**

```llvm
define i32 @h(i32 %x) {
entry:
  %0 = add i32 %x, 1     ; numbered value
  %s = add i32 %0, 1     ; named value
  ret i32 %s
}
```

```bash
$ llvm-as-18 mixed.ll -o /dev/null; echo $?
0
```

**It is legal.** The reverse order is legal too.

**The real rule is**: there is one shared counter, and numbered values must be **monotonically increasing**; skipping numbers is legal, **going backwards is not**.

```llvm
define i32 @f(i32 %x) {
entry:
  %5 = add i32 %x, 1
  %2 = add i32 %5, 1     ; <- goes backwards: error
  ret i32 %2
}
```

```bash
$ llvm-as-18 back.ll -o /dev/null
llvm-as-18: back.ll:4:3: error: instruction expected to be numbered '%6' or greater
  %2 = add i32 %5, 1
  ^
```

The counter's initial value equals the **number of parameters**; **anonymous basic blocks and instructions with results both consume numbers**, while `store`/`br`/`ret` do not. For the full treatment see Chapter 8 of the main text.

### A.1.6 Type equality is not "structural equality"

**The common claim (wrong):** "LLVM's type equality is structural equality; named types are just aliases."

**Actual test:**

```llvm
%A = type { i32, i32 }
%B = type { i32, i32 }

define %A @f(%B %x) {
  ret %A %x
}
```

```bash
$ llvm-as-18 structeq.ll -o /dev/null
llvm-as-18: structeq.ll:4:10: error: '%x' defined with type '%B = type { i32, i32 }' but expected '%A = type { i32, i32 }'
  ret %A %x
         ^
```

**`%A` and `%B` are two different types**, even though their fields are identical.

**The rule**: every `= type` definition creates a distinct **named type**, and a named type is equal only to "the same name". Only **literal** types (written out directly as `{ i32, i32 }`) are compared structurally. A named type and a literal of the same shape are also **not** equal:

```llvm
%A = type { i32, i32 }
define %A @f({ i32, i32 } %x) {
  ret %A %x                     ; <- same error
}
```

**Practical advice**: once you have given a struct a name, use that same name everywhere.

### A.1.7 A missing terminator and a superfluous instruction give the same error

Two completely different mistakes, and `llvm-as` gives **exactly the same** message for both:

```llvm
; case 1: the block has no terminator
define i32 @f(i32 %a) {
entry:
  %x = add i32 %a, 1
}
```

```llvm
; case 2: instructions after the terminator
define i32 @g() {
entry:
  ret i32 0
  %x = add i32 1, 2
}
```

```bash
$ llvm-as-18 no_term.ll -o /dev/null
llvm-as-18: no_term.ll:4:1: error: expected instruction opcode
}
^

$ llvm-as-18 after_term.ll -o /dev/null
llvm-as-18: after_term.ll:5:1: error: expected instruction opcode
}
^
```

**Hint**: when you see `expected instruction opcode`, suspect both possibilities at once. A generator you write yourself should distinguish the two in its internal assertions (Section 14.7 of the main text).

---

## A.2 Version differences (LLVM 18 relative to older versions)

These are not "wrong claims" but **old material that does not apply on LLVM 18**.

### A.2.1 `opt`'s old-style pass syntax has been removed

```bash
$ opt-18 -mem2reg -S input.ll
The `opt -passname` syntax for the new pass manager is not supported, please use `opt -passes=<pipeline>` (or the `-p` alias for a more concise version).
See https://llvm.org/docs/NewPassManager.html#invoking-opt for more details on the pass pipeline syntax.
```

**You must write `-passes=`** (or `-p`):

```bash
opt-18 -passes=mem2reg -S input.ll -o out.ll
opt-18 -p mem2reg -S input.ll -o out.ll          # equivalent
```

### A.2.2 Pointers unified as `ptr` (opaque pointers)

Older material writes `i32*`, `%struct.Point*`. LLVM 18 uses `ptr` uniformly:

| Position | Old spelling (≤14) | LLVM 18 |
|---|---|---|
| Struct field | `getelementptr %struct.P, %struct.P* %p, i32 0, i32 1` | `getelementptr inbounds %struct.P, ptr %p, i32 0, i32 1` |
| Load | `load i32, i32* %p` | `load i32, ptr %p, align 4` |
| Function pointer | `i32 (i32, i32)*` | `ptr` |

**Interestingly**, LLVM 18 is still **lenient** about the old spelling — it silently upgrades it for you:

```bash
$ cat > typedptr.ll <<'EOF'
define i32 @f(i32* %p) {
  %v = load i32, ptr %p
  ret i32 %v
}
EOF
$ llvm-as-18 typedptr.ll -o /dev/null && echo ACCEPTED
ACCEPTED
$ opt-18 -passes=verify -S typedptr.ll
; ModuleID = 'typedptr.ll'
source_filename = "typedptr.ll"

define i32 @f(ptr %p) {          ; <- already rewritten to ptr
  %v = load i32, ptr %p, align 4
  ret i32 %v
}
```

**So "the old spelling still runs" does not mean "the old spelling is right"** — you write `i32*`, and what you read back is `ptr`.

### A.2.3 Tightening of the `disp` type equality rules

See A.1.6. Older LLVM versions had looser type equality rules, and some code that assumed "same structure means equal" now errors out on 18.

### A.2.4 The printing format for floating-point constants

**Common in older material**: `0.1` prints as `0x3FB999999999999A`.

**Measured on LLVM 18**: a decimal that round-trips exactly is printed in decimal preferentially.

```llvm
define dso_local double @dbl_tenth() #0 {
  ret double 1.000000e-01          ; <- not 0x3FB999999999999A
}
```

Only when decimal cannot represent the value exactly does it fall back to the hexadecimal bit pattern:

```llvm
ret double 0x3FBF9ADD3746F65F      ; 0.1234567890123456789
ret float 0x3FB99999A0000000       ; 0.1f
```

**The rule**: LLVM tries to print in decimal; if that decimal string parses back to exactly the same bit pattern, decimal is used, otherwise hexadecimal.

---

## A.3 Metadata and attributes: the entries most easily misremembered from a table

### A.3.1 The behaviour values of module flags

Each entry in `!llvm.module.flags` is `!{behaviour, "name", value}`. The complete table of behaviour values (from LLVM 18's `llvm/IR/Module.h`):

| Value | Name | Meaning |
|---|---|---|
| 1 | `Error` | Error out if the two modules' values disagree |
| 2 | `Warning` | Warn if they disagree, take the first module's value |
| 3 | `Require` | Require another flag to exist after linking with the given value |
| 4 | `Override` | Use this module's value, ignore the other's |
| 5 | `Append` | Append (both values must be metadata nodes) |
| 6 | **`AppendUnique`** | Append and **deduplicate** |
| 7 | `Max` | Take the maximum (the value must be an integer) |
| 8 | `Min` | Take the minimum (the value must be an integer) |

**Note that there is no `Modulo` behaviour** (some material gets this wrong). The enum's legal range is exactly 1–8; write 9 or higher and the verifier rejects it.

In practice the ones you will see most often are:

```llvm
!0 = !{i32 1, !"wchar_size", i32 4}      ; Error level: wchar_t must be 4 bytes
!1 = !{i32 8, !"PIC Level", i32 2}       ; Min: position-independent code level
!4 = !{i32 7, !"frame-pointer", i32 2}   ; Max: frame pointer mode
```

### A.3.2 Two easily confused function attributes

| Attribute | The confusing point |
|---|---|
| `norecurse` | It has nothing to do with `noreturn`; it means "does not recurse directly". The old name was `norecurse` (modern LLVM once called it `norecurse`, now unified) |
| `nounwind` | Means "does not throw exceptions", which is a different thing from "does not return" (`noreturn`) |
| `willreturn` | "Will definitely return", the opposite semantics of `noreturn` |

### A.3.3 The output format of `-print-after-all`

The spelling common in older material is `*** IR Dump After Mem2Reg ***`.

The actual format in LLVM 18 is **`; *** IR Dump After <class name>Pass on <function name or [module]> ***`**; note that **the line starts with `; `** (it is a comment), and that it uses the **pass's class name**:

```
; *** IR Dump After PromotePass on sum_to ***
```

**The class name of `mem2reg` is `PromotePass`** — you write `-passes=mem2reg` on the command line, and the dump shows `PromotePass`. That is why grepping by pass name often finds nothing:

```bash
opt-18 -passes='default<O2>' -print-after-all -S in.ll -o /dev/null 2> trace.txt
grep -n "IR Dump After" trace.txt | head
```

---

## A.4 About the "three lines of IR" claim

This is the single most widely repeated sentence about LLVM IR:

> `int mul_add(int x, int y, int z) { return x*y + z; }` becomes three lines of IR: `mul`, `add`, `ret`.

**Under `-O0` this is not true.** The real `-O0` output has **12 instructions** in the function body:

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

**"Three lines" describes the optimized result** (`-O2` is what gives those three lines):

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) local_unnamed_addr #0 {
  %4 = mul nsw i32 %1, %0
  %5 = add nsw i32 %4, %2
  ret i32 %5
}
```

**Why is `-O0` so verbose?** Two reasons:

1. **To serve the debugger** — the parameters go into stack slots so that gdb can see them at any point during the function's execution;
2. **To translate mutable variables into SSA** — memory is mutable, SSA values are not. Putting variables on the stack is the least effort way to do it.

Chapter 2 of the main text develops this in full, and it is also the starting point of the whole book. It is repeated here because it is so common.

---

## A.5 A self-check list

When you find that "my output does not match the tutorial", check in this order:

1. **Tool version**: is `clang-18 --version` 18.1.3? All output in this book is based on it.
2. **Optimization level**: the difference between `-O0` and `-O2` output can be enormous. Which level was the tutorial's "three lines" about?
3. **`optnone`**: if you run `opt` on `-O0` IR and nothing changes at all, check whether the function's attributes include `optnone` — it **silently** disables every pass (Section 13.6 of the main text).
4. **`opt` syntax**: did you use the removed old-style `-mem2pass` syntax? Switch to `-passes=`.
5. **datalayout and triple**: if a hand-written `.ll` lacks those two lines, LLVM uses the host defaults, and the offsets computed by `getelementptr` may differ.
6. **The error text itself**: `llvm-as` errors sometimes give the same sentence for **two different causes** (see A.1.7). Do not draw a conclusion from one sentence alone.

---

## A.6 Remember the gap between "intuition" and "reality"

This section comes last because it matters more than any single syntax rule.

Every entry collected in this appendix is essentially the same pattern:

> **Your intuition tells you it should be written this way, but LLVM wants it written that way.**

- Hexadecimal looks like it should be `0x2A`, but it is actually `u0x2A`;
- Visibility looks like it should follow a comma, but it actually goes in front;
- `trunc` looks like it should take `nsw` the way `add` does, but it does not;
- Atomic operations look like they should be called `smax` (since `icmp` really is `slt`), but they are called `max`.

**These gaps are not defects in LLVM; they are sediment layers from decades of evolution.** Behind every inconsistency there is a piece of history: some syntax was first designed as A, later B turned out to be more suitable, but A could no longer be changed (it would break compatibility).

So you cannot avoid the traps by "memorizing the rules" — the rules contradict each other. **The only reliable method is: verify as soon as you have written it.**

```bash
llvm-as-18 yourfile.ll -o /dev/null && echo OK
```

That one command blocks the great majority of the traps in this appendix, and it takes one second.

**One last emphasis**: if you read something in this appendix and your terminal gives a different result, **your terminal wins**, and then check the tool version. This book is based on LLVM 18.1.3, and LLVM ships a major version every six months.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 20 Testing, Verification and Optimization](20-ch20-testing-verification-and-optimization.md) · [Next: Appendix B Optimization Primer: From `-O0` to `-O2` →](22-appendix-b-optimization-primer.md)
