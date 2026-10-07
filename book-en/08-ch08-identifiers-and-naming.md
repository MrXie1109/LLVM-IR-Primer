# Chapter 8 Modules, Identifiers and Naming Rules

## 8.1 Referring Back: Where Those `%4`, `%5`, `%9` in Chapter 2 Came From

Do you remember that puzzling detail from Chapter 2?

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  %4 = alloca i32, align 4
```

Three parameters occupy `%0`, `%1`, `%2` — **so why is the first instruction `%4`, and where did `%3` go?**

At the time we approached the answer by measurement: `%3` was taken by the anonymous entry basic block. This chapter **explains it thoroughly** — because this rule directly affects the design decisions you make when writing a compiler (in Chapter 17 we stumble over exactly this).

## 8.2 The Complete Structure of an `.ll` File

First, let us build the overall picture. The textual structure of an LLVM module is:

```llvm
; 1. module-level information
target datalayout = "e-m:e-p270:32:32-..."
target triple = "x86_64-pc-linux-gnu"

; 2. type definitions
%struct.Point = type { i32, i32 }

; 3. global variables
@g = global i32 42, align 4

; 4. Function declarations
declare i32 @printf(ptr, ...)

; 5. function definitions
define i32 @main() {
entry:
  ret i32 0
}

; 6. attribute groups
attributes #0 = { noinline nounwind }

; 7. metadata
!llvm.module.flags = !{!0}
!0 = !{i32 1, !"wchar_size", i32 4}
```

**The order is not mandatory** (apart from a few dependencies), but this is the conventional order. Note:

- **Comments** start with `;` and run to the end of the line.
- **`target triple`** describes the target platform: `<arch><sub>-<vendor>-<sys>-<abi>`.
- **`target datalayout`** describes the data layout: endianness and the various alignments. Chapter 9 takes it apart.
- **Things starting with `!` are metadata**; Chapter 12 covers them.

## 8.3 Three Kinds of Identifiers

Identifiers in IR are distinguished by **prefix** according to their scope:

| Prefix | Name | Scope | Examples |
|---|---|---|---|
| `@` | Global identifier | The whole module | `@main`, `@g_counter`, `@llvm.abs.i32` |
| `%` | Local identifier | Within one function | `%x`, `%4`, `%struct.Point` |
| `!` | Metadata | The whole module | `!0`, `!llvm.module.flags` |

**Note one exception**: a type name (`%struct.Point`) uses `%`, but its scope is **module level**, not function level. It uses `%` only for historical reasons.

## 8.4 Named Values vs Numbered Values: The Core of This Chapter

Local identifiers in LLVM come in two forms:

```llvm
%name      ; named value
%0         ; numbered / unnamed value
```

**The two can coexist in the same function**: named values do not participate in the numbering counter, while numbered values must appear in **monotonically increasing** order according to that counter.

```llvm
define i32 @h(i32 %x) {
entry:
  %0 = add i32 %x, 1     ; numbered value
  %s = add i32 %0, 1     ; named value, mixed with a numbered one
  ret i32 %s
}
```

The code above is legal (`llvm-as-18` accepts it).

What really does produce an error is a **number going backwards**:

```llvm
define i32 @f(i32 %x) {
entry:
  %5 = add i32 %x, 1
  %2 = add i32 %5, 1     ; <- back from 5 to 2
  ret i32 %2
}
```

```bash
$ llvm-as-18 back.ll -o /dev/null
llvm-as-18: back.ll:4:3: error: instruction expected to be numbered '%6' or greater
  %2 = add i32 %5, 1
  ^
```

The error message is accurate: since the previous number is `%5`, the next one must be **≥ 6**.

So the rule is:

> **Inside one function, numbered values share a single counter. The initial value of the counter equals "the number of parameters". Every time something that "needs a number" is encountered, the counter increases by one. The number written for a numbered value must be greater than or equal to the current counter.**

Note that the last sentence says "greater than or equal to", not "equal to" — you may skip numbers (writing `%9` directly after `%5`), but you may not go backwards. Skipped numbers are simply wasted, which does not affect correctness.

The things that "need a number" are:

1. **Parameters** (if the parameter has no name);
2. **Basic blocks** (if the block has no name);
3. **Instructions that produce a value** (if the instruction's result has no name).

Instructions that **do not produce a value**, such as `store`, `br` and `ret`, do not take a number.

### Verifying It One by One

**Example one: `mul_add`, 3 parameters.**

```
params %0, %1, %2      -> counter = 3
entry block unnamed    -> takes %3, counter = 4
%4 = alloca ...        -> takes %4, counter = 5
%5 = alloca ...       → %5
%6 = alloca ...       → %6
store ...              -> takes no number
%7 = load ...         → %7
...
```

**`%3` is that anonymous entry basic block.** Puzzle solved.

**Example two: `one(int a)`, 1 parameter.**

```llvm
define dso_local i32 @one(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
```

```
param %0               -> counter = 1
entry block unnamed    -> takes %1, counter = 2
%2 = alloca ...        -> %2          OK, matches measurement
```

**Example three: `two(int a, int b)`, 2 parameters.**

```llvm
define dso_local i32 @two(i32 noundef %0, i32 noundef %1) #0 {
  %3 = alloca i32, align 4
```

```
params %0, %1          -> counter = 2
entry block unnamed    -> takes %2, counter = 3
%3 = alloca ...        -> %3          OK, matches measurement
```

**Example four: a function with branches**, the most intuitive one:

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

7:                                                ; preds = %1
  store i32 2, ptr %2, align 4
  br label %8

8:                                                ; preds = %7, %6
  %9 = load i32, ptr %2, align 4
  ret i32 %9
}
```

`%6`, `%7` and `%8` are **all basic blocks**, not values. And the comment `; preds = %1` leaks the fact that the name of the entry block is `%1`.

### Naming a Block Changes the Numbering

Because "something with a name does not take a number", giving the entry block a name shifts every later number forward by one:

```llvm
define i32 @named(i32 %x) {
entry:                    ; <- the entry block is named, so it takes no number
  %1 = add i32 %x, 1      ; <- the parameter took %0, so this is %1
  ret i32 %1
}
```

Measured: `llvm-as-18` accepts it.

**But if the block has no name**, the same code must be written with `%2`:

```llvm
define i32 @named(i32 %x) {
  %2 = add i32 %x, 1      ; <- the anonymous entry block took %1
  ret i32 %2
}
```

Both versions are correct; the only difference is whether the block has a name. **This is why we name the entry block `entry` in the skeleton of Chapter 14** — besides readability, it also makes the numbering more intuitive.

## 8.5 Which Characters Are Allowed in a Name

### The Character Set for Named Values

After `%` or `@`, a name may be:

- letters, digits, underscores, dots (`.`) and hyphens (`-`);
- **but it may not start with a digit** (otherwise it would be parsed as a number).

Legal:

```llvm
%x
%my_var
%t1
%struct.Point
%a-b
%.hidden
```

Illegal:

```llvm
%1abc      ; starts with a digit
%my var    ; contains a space
```

The error for the first case is rather distinctive:

```bash
$ llvm-as-18 badname.ll -o /dev/null
llvm-as-18: badname.ll:3:5: error: expected '=' after instruction id
  %1abc = add i32 %x, 1
    ^
```

The parser reads `%1`, assumes it is a numbered value, then expects an `=` and instead runs into `a`, so it reports "expected '=' after instruction id". **Remember this error message**: seeing it almost always means you have a "name that starts with a digit".

### Names That Need Escaping

If a name contains special characters, quotes are needed:

```llvm
%"weird name with spaces" = add i32 1, 2
@"global with space" = global i32 0
```

clang occasionally generates names like this for anonymous types in C.

### The Scope of Local Names

**The scope of a named value is the whole function** (not the block). So:

```llvm
define i32 @f(i32 %x) {
entry:
  %a = add i32 %x, 1
  br label %next
next:
  %b = add i32 %a, 1     ; %a is visible in the next block
  ret i32 %b
}
```

This is legal. But note: **visible ≠ dominates**. `%a` is legal here because `entry` dominates `next`. If it were the other way round, the verifier would report "Instruction does not dominate all uses" (as discussed in Chapter 14).

## 8.6 Metadata Identifiers

Things starting with `!` are metadata:

```llvm
!0 = !{i32 1, !"wchar_size", i32 4}
!llvm.module.flags = !{!0}
```

- `!0`, `!1` are **numbered metadata**; they are module-level and can be referenced.
- `!llvm.module.flags`, `!llvm.ident` are **named metadata**.
- `!"string"` is a **metadata string**.

Metadata does not participate in code generation; it only supplies extra information to the optimizer (Chapter 12 covers the details).

## 8.7 A Digression: Why This Numbering Rule Is a Trap for Compiler Authors

In Chapter 17 we will write a code generator. Imagine a naive implementation:

```python
class Function:
    def __init__(self):
        self.temp = 0
    def new_temp(self):
        self.temp += 1
        return f"%{self.temp}"     # <- dangerous!
```

It maintains its own counter, starting at 1. The generated IR is roughly:

```llvm
define i32 @l_fib(i32 %n) {
entry:
  %1 = icmp slt i32 %n, 2
  br i1 %1, label %2, label %3
...
```

**This will fail**, because the generator must simulate exactly the single counter shared by "parameters, anonymous basic blocks and instructions with results". As soon as it inserts a block somewhere and forgets to synchronize the counter, every later number is off.

And what makes it worse is that **skipping numbers is legal while going backwards is not**. This means you cannot bluff your way through by "writing the numbers a bit larger" — once the counter does not match, you may write a number that is too small (an error), or you may happen to write one that is large enough (it verifies, but the numbering is out of step with the real structure, which is extremely hard to debug).

A code generator that maintains its own numbering counter will hit this kind of error if it forgets that "an anonymous basic block also takes a number". Below is a minimal example you can reproduce yourself — note that the numbering goes backwards from `%6` to `%4`:

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

(The source file lives at `code/part2-ir/numfail.ll`. It is a piece of IR that is **deliberately wrong**, used to reproduce this error.)

The meaning is: the generator thought "`%4` is next", but LLVM's counter has already grown to 12. The gap comes from the generator inserting a basic block without synchronizing its own counter.

**The solution**: use **named values** throughout. Give every temporary value a name such as `%t1`, `%t2`, and the whole implicit counting scheme is bypassed — named values do not participate in the numbering counter and are not constrained by it.

```python
def new_temp(self):
    self.temp += 1
    return f"%t{self.temp}"     # named value, safe
```

It generates:

```llvm
define i32 @l_fib(i32 %n) {
entry0:
  %t1 = icmp slt i32 %n, 2
  br i1 %t1, label %then1, label %else2
...
```

The parameters are named values, the temporaries are named values, the block labels are named values — **there are no numbered values at all, and the rule does not apply in the slightest**. Concise, readable, and impossible to trip over.

> **This is not circumventing the rule, but an engineering choice made after understanding it.** LLVM's numbering scheme exists to keep *automatically generated* IR compact (numbers are shorter than names), but for a scenario like ours that values debuggability, named values are clearly more suitable.

## 8.8 Exercises

**Exercise 8.1** Hand-write an `.ll` whose function has 2 parameters and whose entry block **has a name**. Work out what number the first instruction should have, then verify it with `llvm-as-18`.

**Exercise 8.2** Deliberately mix named values and numbered values in the same function and record the complete error from `llvm-as-18`.

**Exercise 8.3** Write a function whose first instruction is `%3`. How many parameters should it have? Should the entry block have a name?

**Exercise 8.4** Do a round trip with `llvm-as-18` + `llvm-dis-18`:

```bash
llvm-as-18 my.ll -o my.bc
llvm-dis-18 my.bc -o -
```

Observe whether your named values are preserved. Then try a version that is all numbered values.

**Exercise 8.5** Generate the `-O0` IR of any C function and, against the rules in Section 8.4, manually verify the owner of each of the first 10 numbers (a parameter, a block, or an instruction).

## 8.9 Summary

- Three kinds of identifiers: `@` (global), `%` (local to a function, with type names as the exception), `!` (metadata).
- Local identifiers have two forms, **named values** and **numbered values**, and the two **can coexist**; the constraint is that numbered values must be **monotonically increasing** according to the shared counter (skipping is legal, going backwards is not).
- The numbering counter starts at "the number of parameters"; **anonymous basic blocks and instructions with results both take a number**, while `store`/`br` do not.
- Naming a basic block saves a number.
- A named value must not start with a digit; special characters require quotes.
- **When writing a code generator, use named values throughout**, which bypasses the numbering rules completely.

In the next chapter we explain the type system — including that long mysterious string in `target datalayout`.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 7 Functions, Calling Conventions and Linkage](07-ch07-functions-and-calls.md) · [Next: Chapter 9 The Type System →](09-ch09-the-type-system.md)
