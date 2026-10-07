# Chapter 10 Constants, Global Variables and Linkage

## 10.1 Referring back: `@g_counter` from Chapter 6 and `null` from Chapter 4

In Chapter 6 we wrote:

```c
int g_counter = 42;
const int g_limit = 100;
```

```llvm
@g_counter = dso_local global i32 42, align 4
@g_limit = dso_local constant i32 100, align 4
```

And in Chapter 4 we saw:

```llvm
%2 = icmp eq ptr %0, null
```

At the time we said "`null` is IR's keyword for the empty pointer value". This chapter sets both matters straight at once: **IR's constant system**, and **every modifier form of a global variable**.

## 10.2 Constants at a glance

A constant in IR can appear anywhere a value is needed; there is no need to allocate a variable first.

### Integer and floating point constants

```llvm
i32 42            ; decimal
i32 -1            ; negative (iN allows negative literals)
i32 052           ; octal (leading 0)
u0x2A             ; hexadecimal: must carry the u (unsigned) or s (signed) prefix
s0x2A             ; signed hexadecimal
double 1.0
double 0x4014000000000000    ; the hexadecimal bit pattern of a floating point value
float 0.000000e+00           ; the usual format clang prints for float
half 0xH3C00
```

**Two counter-intuitive points**: hexadecimal must be written `u0x2A` / `s0x2A`, not `0x2A`; and LLVM IR has **no binary literals**. The corresponding error message is misleading (it mentions "floating point"); see [Appendix A.1.1](21-appendix-a-differences-from-common-claims.md#a11-integer-constants-have-no-bare-hexadecimal-and-no-binary-either).

### Boolean constants

```llvm
i1 true
i1 false
```

`true` is just `i1 1` and `false` is `i1 0`. Both spellings are legal, but `true`/`false` are more readable — that is where the `phi i1 [ false, %2 ], [ %9, %7 ]` from Chapter 4 comes from.

### Null and undefined values — three concepts you must tell apart

This is the most subtle set of concepts in IR. **`null`, `undef`, and `poison` are three different things.**

#### `null`

```llvm
ptr null                      ; the null pointer
```

`null` is **the zero value of a pointer**. Like any other value it is determinate — you can compare it, pass it, return it from a function. C's `NULL` compiles to `ptr null`.

A historical note: in older versions of LLVM the zero value of an aggregate type was also written with `null` (as in `[10 x i32] null`). Nowadays `zeroinitializer` is recommended.

#### `undef`

```llvm
i32 undef
```

`undef` means: **"I don't care about this value; give me whatever you like."**

The key property: **every read of `undef` may produce a different value.**

```llvm
%a = undef
%b = add i32 %a, %a       ; not 2*%a! because the two %a can take different values
```

The optimizer may replace `undef` with any constant. Hence:

```llvm
%x = icmp eq i32 undef, undef    ; the optimizer may replace this with true or false, whatever it likes
```

#### `poison`

```llvm
i32 poison
```

`poison` is stronger: **it is a "poisoned" value; the result of any operation that depends on it is also poison, and once poison affects "observable behaviour" (say as the condition of a `br`, or as the value stored by a `store`), the behaviour is undefined.**

This is exactly the mechanism behind `nsw` and `inbounds`: when their condition is not met they **produce poison** rather than a wrong number.

```llvm
%r = add nsw i32 2147483647, 1     ; signed overflow → %r is poison
```

If `%r` is later used in a branch, the program is UB; if `%r` is discarded, nothing happens. **This is why the optimizer can confidently fold `x + 1 > x` to `true`** (Chapter 3) — on overflow the result is poison, poison used in a comparison is still poison, and poison used in a branch is UB, that is, "the programmer broke the contract".

#### `freeze`

The `freeze` instruction "freezes" an `undef` or a `poison`:

```llvm
%f = freeze i32 poison     ; %f becomes some determinate, arbitrary value
```

After `freeze` the value is determinate and no longer poisoned. Its purpose is to turn a program that would otherwise be UB into one that is "nondeterministic but not undefined" — this makes certain optimizations (such as vectorization during loop unrolling) safe in the presence of `undef`.

A complete program using `freeze`, measured:

```llvm
define i32 @f(i1 %c) {
  %p = select i1 %c, i32 1, i32 poison
  %fr = freeze i32 %p
  ret i32 %fr
}

define i32 @u() {
  ret i32 undef
}
```

```bash
$ llvm-as-18 poison.ll -o /dev/null && echo OK
OK
```

### Aggregate constants

```llvm
[3 x i32] [i32 1, i32 2, i32 3]         ; array constant
{ i32, i32 } { i32 1, i32 2 }           ; struct constant
<4 x i32> <i32 1, i32 2, i32 3, i32 4>  ; vector constant
[3 x i32] zeroinitializer               ; all zeros
[3 x i32] undef                         ; all undef
[3 x i32] poison                         ; all poison
```

`zeroinitializer` is shorthand for "set every field to its zero value" and works for any type. It is extremely common in the zero initialization of global variables.

## 10.3 Global variables

### The basic form

```llvm
@g = global i32 42, align 4               ; writable
@c = constant i32 7, align 4              ; read-only
@arr = global [5 x i32] [i32 1, i32 2, i32 3, i32 4, i32 5], align 16
@zeroinit = global [100 x i32] zeroinitializer, align 16
@ext = external global i32, align 4       ; defined elsewhere
```

The syntax is:

```llvm
@name = [linkage] [visibility] global|constant <type> <initial value>, <alignment>
```

### String constants

A C string literal:

```c
char *greeting(void) { return "hello"; }
```

```llvm
@.str = private unnamed_addr constant [6 x i8] c"hello\00", align 1
```

Three key points:

1. **The type is `[6 x i8]`** — `"hello"` has 5 characters, and with the trailing `\0` that makes 6 bytes. **A C string always carries its trailing `\0`, and the array length in IR counts it.**
2. **`c"hello\00"`** is IR's string literal syntax: the `c` prefix + quotes + escape sequences. `\00` is that trailing NUL.
3. **`private` and `unnamed_addr`** — the string is produced inside the compiler; it need not be visible externally, nor does it need a stable address.

The escape sequences are similar to C: `\00` (octal), `\0A` (newline), `\22` (double quote), `\5C` (backslash). **Note that these are all hexadecimal or octal numeric codes, not letter escapes like `\n`.**

### The complete linkage table

```llvm
@pub = global i32 1                      ; default: externally visible
@priv = private global i32 2             ; module only, does not go into the symbol table
@internal = internal global i32 3        ; module only, goes into the symbol table (C's static)
@weak = weak global i32 4                ; weak symbol, may be overridden
@common = common global i32 0            ; C's tentative definition
@ext = external global i32               ; defined elsewhere
@tl = thread_local global i32 6          ; thread-local storage
```

| Linkage | Corresponding C | Meaning |
|---|---|---|
| (none) | ordinary global variable | externally visible |
| `internal` | `static` | visible inside the module, present in the symbol table (`local` binding) |
| `private` | no direct equivalent | visible inside the module, does **not** appear in the symbol table |
| `external` | `extern` declaration | defined elsewhere |
| `weak` | `__attribute__((weak))` | may be overridden by a stronger definition |
| `linkonce` | template instantiation | may be defined repeatedly, one copy is kept |
| `available_externally` | — | used only for optimization, no code is generated |
| `common` | `int x;` (tentative definition) | may be merged with other `common` symbols |
| `appending` | — | used only for special purposes such as `llvm.global_ctors` |

**The difference between `internal` and `private`** matters in practice:

- an `internal` symbol still appears in the object file's symbol table (marked local), so a debugger can see it;
- a `private` symbol may be eliminated or renamed entirely, and the debugger cannot see it.

For C's `static`, clang uses `internal` (for the debugging experience), and for internal symbols it generates itself (such as string literals) it uses `private`.

### Visibility

Besides linkage, there is **visibility**.

**Mind the syntax**: visibility is a **prefix keyword**, written **before** `global`/`constant`, not a property after the comma:

```llvm
@v = protected global i32 1
@h = hidden global i32 2
```

(Writing `@v = global i32 1, visibility protected` is rejected with `unknown global variable property!` — see [Appendix A.1.2](21-appendix-a-differences-from-common-claims.md#a12-a-global-variables-visibility-is-a-prefix-not-a-comma-attribute).)

| Visibility | Meaning |
|---|---|
| `default` | normal, may be overridden externally (this is what you get when you omit it) |
| `hidden` | not exported to the dynamic symbol table, cannot be overridden externally |
| `protected` | exported but not overridable |

These mainly affect shared libraries. `-fvisibility=hidden` simply adds `hidden` to every symbol.

clang's output, measured:

```c
__attribute__((visibility("hidden"))) int hg = 1;
__attribute__((visibility("protected"))) int pg = 2;
```

```llvm
@hg = hidden global i32 1, align 4
@pg = protected global i32 2, align 4
```

### Sections

```llvm
@s = global i32 1, section ".mysec"
```

This corresponds to C's `__attribute__((section(".mysec")))`. It is used to place data into a particular section (such as read-only data, or a section defined by a custom linker script).

## 10.4 What `dso_local` is

Look back at the output from Chapter 2:

```llvm
@g_counter = dso_local global i32 42, align 4
define dso_local i32 @mul_add(...) #0 {
```

`dso_local` **is not a linkage**; it is a separate marker: "this symbol will be resolved inside the current dynamic shared object (DSO)".

**Why is it valuable?** Because it allows more efficient code generation:

- **with `dso_local`**: it may be assumed that the symbol will not be overridden by another DSO, so accesses do not have to go through the GOT/PLT and can use relative addressing directly;
- **without `dso_local`**: the symbol may be replaced by interposition, so the GOT/PLT must be used.

When compiling an executable on Linux, clang adds `dso_local` by default (because an executable's symbols are usually not preemptible). When compiling a shared library (`-fPIC`) it has to be more careful.

## 10.5 Accessing global variables

```c
int get_counter(void) { return g_counter; }
void bump(void) { g_counter++; }
int* addr_of(void) { return &g_counter; }
```

```llvm
define dso_local i32 @get_counter() #0 {
  %1 = load i32, ptr @g_counter, align 4
  ret i32 %1
}

define dso_local void @bump() #0 {
  %1 = load i32, ptr @g_counter, align 4
  %2 = add nsw i32 %1, 1
  store i32 %2, ptr @g_counter, align 4
  ret void
}

define dso_local ptr @addr_of() #0 {
  ret ptr @g_counter
}
```

Three important observations:

1. **`@g_counter` is itself a pointer.** `load i32, ptr @g_counter` reads the value straight from the global variable's address — there is no need to `alloca` first and store the address.
2. **`store i32 %2, ptr @g_counter`** works the same way, writing directly.
3. **`ret ptr @g_counter`** — taking the address is just "using the global variable's name as a value". **`&g_counter` has no corresponding instruction in IR**, because the name of a global variable already is an address.

This explains why global variables are handled differently from local variables: **a local variable needs an `alloca` to get an address, whereas a global variable's address is its name.**

## 10.6 Constant expressions

IR allows **compile-time computation** in constant positions:

```llvm
@pi_ptr = global ptr getelementptr (i32, ptr @pi, i64 1)
```

Here `getelementptr` appears in a **constant** position. IR supports a set of constant expressions:

| Expression | Meaning |
|---|---|
| `getelementptr` | constant address computation |
| `bitcast` | bit reinterpretation (rarely used in LLVM 18 now that `ptr` unifies pointers) |
| `inttoptr` / `ptrtoint` | convert between integers and pointers |
| `add` / `sub` | constant addition and subtraction of integers |
| `trunc` / `zext` / `sext` | integer width conversions |
| `select` | constant conditional selection |

**Note: constant expressions are far less powerful than runtime instructions.** For example, you cannot write `sdiv` in a constant (because division by zero is unpredictable).

A constant GEP, measured:

```llvm
%struct.Point = type { i32, i32 }
@p = global %struct.Point { i32 1, i32 2 }
@y_ptr = global ptr getelementptr inbounds (%struct.Point, ptr @p, i32 0, i32 1)
```

```bash
$ llvm-as-18 constexpr.ll -o /dev/null && echo OK
OK
```

## 10.7 Exercises

**Exercise 10.1** Generate C functions returning `0.1`, `0.5`, and `0.25`, and observe which use decimal notation and which use hexadecimal bit patterns. Explain why.

**Exercise 10.2** Use `llvm-as-18` to check which of the following passes validation, and explain:

```llvm
; A
define i32 @f() {
  %x = add i32 undef, 1
  ret i32 %x
}

; B
define i32 @g() {
  %x = add i32 poison, 1
  ret i32 %x
}
```

**Both pass validation.** Then run `instcombine` once:

```bash
$ opt-18 -passes=instcombine -S undefp.ll
```

```llvm
define i32 @f() {
  ret i32 undef
}

define i32 @g() {
  ret i32 poison
}
```

The optimizer folded `undef + 1` to `undef` and `poison + 1` to `poison`. This confirms the semantics of the two:

- the result of `undef + 1` is still "any value at all", so it is still `undef`;
- `poison + 1` is contaminated by poison, so it is still `poison`.

**Note that `poison` propagates more strongly**: once a value is `poison`, every value computed from it is `poison`, and once `poison` affects observable behaviour the program is UB. This is the mechanism by which `nsw`/`inbounds` authorize aggressive optimization.

**Exercise 10.3** Write a C program containing a `static` global variable, an ordinary global variable, a `const` global variable, and a string literal. Generate IR, point out which linkage each one uses, and check symbol visibility with `llvm-nm-18`:

```bash
clang-18 -c -emit-llvm prog.c -o prog.bc
llvm-nm-18 prog.bc
```

**Exercise 10.4** Hand-write a `.ll` file that defines a global array `@table = global [4 x i32] [i32 10, i32 20, i32 30, i32 40]`, and write a function that reads out element `i` using `getelementptr` + `load`. Test it with a C driver.

**Exercise 10.5** Explain why `@g_counter` can be used directly as the address for a `load`, whereas the local variable `x` must first be `alloca`'d and `store`'d before its address can be taken.

**Exercise 10.6 (thought question)** What is the difference between `undef` and `poison`? Why are two different concepts needed? Hint: think about what different assumptions the optimizer may make about `x` in `x * 2` depending on whether `x` is `undef` or `poison`.

## 10.8 Summary

- Constants can be integers, floating point values, booleans, `null`, `undef`, `poison`, aggregate constants, or `zeroinitializer`.
- **Floating point constants must be exactly representable**; clang prints a hexadecimal bit pattern for values that are not.
- **`null` is a determinate zero value, `undef` may differ on every read, and `poison` contaminates downstream operations and may cause UB.**
- `zeroinitializer` is shorthand for all zeros and applies to any type.
- A string literal is `[N x i8]`, **its length includes the trailing `\0`**, and it uses the `c"...\00"` syntax.
- Linkage and visibility determine a symbol's behaviour at link time; `internal` keeps a symbol table entry (good for debugging), `private` does not.
- `dso_local` is not a linkage; it allows more efficient address access.
- **A global variable's name is itself an address**, so `&g` has no corresponding instruction in IR.
- Constant expressions support a small set of operations such as `getelementptr`.

Next chapter we work through all the instructions systematically.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 9 The Type System](09-ch09-the-type-system.md) · [Next: Chapter 11 The Instruction Reference →](11-ch11-instruction-reference.md)
