# Chapter 6 Memory, Pointers and `getelementptr`

## 6.1 Global Variables

Start with the simplest case:

```c
int g_counter = 42;
const int g_limit = 100;

int get_counter(void) { return g_counter; }
```

`-O0`:

```llvm
@g_counter = dso_local global i32 42, align 4
@g_limit = dso_local constant i32 100, align 4

define dso_local i32 @get_counter() #0 {
  %1 = load i32, ptr @g_counter, align 4
  ret i32 %1
}
```

A few points:

1. **Global variables use the `@` prefix**, and so do functions. Local values use `%`.
2. **`global` vs `constant`**: a variable qualified with `const` becomes `constant`. This is not just documentation — it promises the optimizer that "this memory will not be written", so it can be placed in a read-only section and all its `load`s can be constant-propagated.
3. **`align 4`**: the alignment requirement.
4. **`load i32, ptr @g_counter, align 4`** — the name `@g_counter` of a global variable is itself a **pointer** (the address of that storage), so it can be used directly as the address operand of a `load` without an `alloca` first.

### `static` and `extern`

```c
int g_pub = 1;              /* ordinary definition */
static int s_hidden = 7;    /* visible within this module only */
extern int g_ext;           /* declared only, not defined */
int use_ext(void) { return g_ext; }   /* it must actually be used, or nothing appears in the IR */
```

```llvm
@g_pub = dso_local global i32 1, align 4
@s_hidden = internal global i32 7, align 4
@g_ext = external global i32, align 4

define dso_local i32 @use_ext() #0 {
  %1 = load i32, ptr @g_ext, align 4
  ret i32 %1
}
```

> **An easily confusing point**: if the source contains only `extern int g_ext;` and **no function uses it**, then the IR clang generates **will not contain the line `@g_ext`** — because nothing references it, so the module does not need that declaration. The example above deliberately adds `use_ext` to make it show up.

| C | IR linkage | Meaning |
|---|---|---|
| `static` | `internal` | Visible only in the current module; the linker cannot see it |
| `extern` (declaration) | `external` | Defined elsewhere; this module only references it |
| no qualifier (definition) | (the default, i.e. `external`) | Defined in this module and visible to the outside |

Note that `@g_ext = external global i32, align 4` **has no initializer** — because it is not defined here.

This also explains a phenomenon that Chapter 7 discusses: an `extern` global variable, like an `extern` function, leaves an "unresolved" symbol in the module.

## 6.2 `alloca` Revisited and Its Lifetime

We saw `alloca` in Chapter 2. Here are a few extra points.

```llvm
%p = alloca i32, align 4          ; one i32
%q = alloca i32, i32 10, align 16 ; 10 i32s (C's VLA)
```

The second form of `alloca` carries an element count and is used for variable-length arrays (VLAs).

**The lifetime of an `alloca` ends when the function returns.** It allocates on the stack frame and does not need to (and cannot) be freed manually. This point matters: **there is no `free` in IR**. When you need to manage memory manually, you call C's `malloc`/`free`; `alloca` is automatic.

At `-O0` all `alloca`s are clustered at the beginning of the entry block — this is not a syntactic requirement (`alloca` may appear in any block) but clang's code generation strategy, and it is also the strategy of the compiler in Part III (the `alloca_slot`/`entry_allocas` of Chapter 17 do exactly this).

## 6.3 `getelementptr`: The Most Misunderstood Instruction in LLVM IR

`getelementptr` is usually abbreviated **GEP**. It does exactly one thing:

> **Compute an address, without performing any memory access.**

This must be burned into your brain first. **GEP does not read memory and does not write memory; it only does pointer arithmetic.** Reading uses `load`, writing uses `store`.

### 6.3.1 Array Elements

```c
int get_elem(int *a, int i) { return a[i]; }
```

`-O0`:

```llvm
define dso_local i32 @get_elem(ptr noundef %0, i32 noundef %1) #0 {
  %3 = alloca ptr, align 8
  %4 = alloca i32, align 4
  store ptr %0, ptr %3, align 8
  store i32 %1, ptr %4, align 4
  %5 = load ptr, ptr %3, align 8
  %6 = load i32, ptr %4, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds i32, ptr %5, i64 %7
  %9 = load i32, ptr %8, align 4
  ret i32 %9
}
```

The three key lines:

```llvm
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds i32, ptr %5, i64 %7
  %9 = load i32, ptr %8, align 4
```

- **`sext i32 %6 to i64`** — C's `int` is 32 bits, but **pointer arithmetic uses 64 bits on a 64-bit platform**. So the index must first be sign-extended from `i32` to `i64`. This "out of nowhere" conversion is very common; do not be surprised to see `sext` right before `getelementptr`.
- **`getelementptr inbounds i32, ptr %5, i64 %7`** — computes `%5 + %7 * sizeof(i32)`.
- **`load`** — actually reads the value out.

### 6.3.2 How to Read GEP's Operands

```llvm
getelementptr inbounds i32, ptr %5, i64 %7
              ^^^^^      ^^^^   ^^^^^^
              (1)        (2)    (3)
```

1. **`i32` (source element type)** — "treat `%5` as a pointer to `i32`".
2. **`ptr %5` (base address)** — where to start counting from.
3. **`i64 %7` (index)** — how many `i32`s to advance by.

**Note that `sizeof` is automatic.** GEP knows `i32` is 4 bytes, so `%7 = 3` means advancing 12 bytes. You **do not** need to multiply by 4 yourself.

This is exactly the reason GEP exists: **it makes pointer arithmetic target-independent**. On a 32-bit platform the index width differs and the alignment of `i32` may differ, yet your GEP code needs no change at all.

### 6.3.3 `inbounds`: A Promise You Must Understand

`inbounds` means:

> "The result of this arithmetic is still **inside** the original object (or points exactly one position past the end). If not, the result is `poison`."

This is a **promise**, like `nsw`. It gives the optimizer power:

- since it will not run outside the object, "pointer comparisons" have well-defined behaviour;
- since it will not run outside the object, `p + 1` cannot wrap around (the address does not overflow);
- therefore these address computations can be reordered, merged and eliminated more freely.

**The price is: if you lie (and really do run outside the object), the behaviour is undefined.** In C, an out-of-bounds array access is UB anyway, so clang can add `inbounds` without worry.

A hand-written GEP **may omit `inbounds`**; that is legal, it just offers fewer optimization opportunities:

```llvm
%p = getelementptr i32, ptr %base, i64 %i     ; legal, but without inbounds
```

**Negative indices are also legal**:

```llvm
%r = getelementptr inbounds i32, ptr %base, i64 -1   ; one element backwards
```

### 6.3.4 Struct Fields

This is where GEP confuses people most, because it needs **two indices**.

```c
struct Point { int x; int y; };

int get_y(struct Point *p) { return p->y; }
void set_x(struct Point *p, int v) { p->x = v; }
```

`-O0`:

```llvm
%struct.Point = type { i32, i32 }

define dso_local i32 @get_y(ptr noundef %0) #0 {
  %2 = alloca ptr, align 8
  store ptr %0, ptr %2, align 8
  %3 = load ptr, ptr %2, align 8
  %4 = getelementptr inbounds %struct.Point, ptr %3, i32 0, i32 1
  %5 = load i32, ptr %4, align 4
  ret i32 %5
}

define dso_local void @set_x(ptr noundef %0, i32 noundef %1) #0 {
  %3 = alloca ptr, align 8
  %4 = alloca i32, align 4
  store ptr %0, ptr %3, align 8
  store i32 %1, ptr %4, align 4
  %5 = load i32, ptr %4, align 4
  %6 = load ptr, ptr %3, align 8
  %7 = getelementptr inbounds %struct.Point, ptr %6, i32 0, i32 0
  store i32 %5, ptr %7, align 4
  ret void
}
```

Look at that double index:

```llvm
%4 = getelementptr inbounds %struct.Point, ptr %3, i32 0, i32 1
                                              ^^^^^^  ^^^^^^
                                              (1)     (2)
```

**The first index `i32 0`:** this is the **pointer dereference step**. It is almost always 0, meaning "do not move the pointer, just use where it currently points". If `%3` points to an **array** of `struct Point` and you want the second element, you write `i32 1` here.

**The second index `i32 1`:** this is the **struct field number**. `Point` is `{ i32, i32 }`, field 0 is `x` and field 1 is `y`.

So the whole sentence reads: "treat `%3` as a pointer to `%struct.Point`, do not move it, and take its field number 1".

> **Mnemonic**: **the first index is the "array subscript", the second is the "field number".** Array access needs only the first index (and usually `i64` because it must be sign-extended), while struct access needs both.

### Why Is the First Index There at All?

Because it lets "an array of structs" and "a single struct" be expressed by the same instruction:

```llvm
; the y field of a single Point
%a = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1

; the y field of the 3rd Point (p is an array of Point)
%b = getelementptr inbounds %struct.Point, ptr %p, i64 3, i32 1
```

In the second one the first index becomes `i64 3`, and **the index type changes from `i32` to `i64`** — because array indices need 64-bit addressing capability. This type change is a clang convention (an `i32` is enough for a struct field number, while an array index uses `i64`); it is not a syntactic requirement.

### 6.3.5 Diagnosing Common `getelementptr` Mistakes

**Mistake one: thinking GEP reads memory.**

```llvm
%v = getelementptr inbounds i32, ptr %p, i64 0   ; %v is ptr, not i32
```
The result of a GEP is **always `ptr`** (in LLVM 18). To get the value you must `load` it.

**Mistake two: forgetting the `load`.**

```llvm
%v = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1
ret i32 %v        ; <- type error: %v is ptr, not i32
```

```
llvm-as-18: error: '%v' defined with type 'ptr' but expected 'i32'
```

**Mistake three: thinking the index is a byte offset.**

A GEP index is a count of **elements**, not bytes. `getelementptr i32, ptr %p, i64 1` advances 4 bytes, not 1 byte. To move by bytes, use `i8` as the element type.

## 6.4 Arrays

```c
int sum_arr(int *a, int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
```

The core part at `-O0`:

```llvm
11:                                               ; preds = %7
  %12 = load ptr, ptr %3, align 8
  %13 = load i32, ptr %6, align 4
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds i32, ptr %12, i64 %14
  %16 = load i32, ptr %15, align 4
  %17 = load i32, ptr %5, align 4
  %18 = add nsw i32 %17, %16
  store i32 %18, ptr %5, align 4
  br label %19
```

`a[i]` → `sext` + `getelementptr inbounds i32, ptr %12, i64 %14` + `load`. Exactly the same as what we hand-wrote earlier.

## 6.5 Struct Type Definitions

Note the line `%struct.Point = type { i32, i32 }`, which comes before the functions:

```llvm
%struct.Point = type { i32, i32 }
```

This is a **type definition**, not a variable. `%struct.Point` is a **named type**. `{ i32, i32 }` is a **literal type** (an anonymous struct type).

LLVM's naming rules:

- an identifier starting with `%name` that is defined at module level with `= type` is a named type;
- `%struct.X` is the conventional name clang generates for C's `struct X`;
- `{ i32, i32 }` is an anonymous struct and may be used inline, but every time you write it out it counts as the same type (struct type equality is **structural equivalence**).

Look at a mixed one:

```c
struct Mixed { char c; int i; double d; };
```

clang generates:

```llvm
%struct.Mixed = type { i8, i32, double }
```

Note that `char` becomes `i8`, `int` is `i32`, and `double` is `double`. **There are no names like `char`/`short`/`int`/`long` in IR** — only `iN`. Chapter 9 covers this mapping.

## 6.6 Exercises

**Exercise 6.1** Generate the `-O2` IR for `int get_elem(int *a, int i)`. The measured result is:

```llvm
define dso_local i32 @get_elem(ptr nocapture noundef readonly %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = sext i32 %1 to i64
  %4 = getelementptr inbounds i32, ptr %0, i64 %3
  %5 = load i32, ptr %4, align 4, !tbaa !5
  ret i32 %5
}
```

**The `sext` is still there.** Why does the optimizer not simply use an `i32` index? Because the index semantics of `getelementptr` are "move by elements", and address arithmetic on a 64-bit platform must be done with 64-bit integers — the index width determines the **wrapping behaviour when the address is computed**. Using an `i32` index means "first compute the offset in 32 bits, then widen to 64 bits", which gives a different result when the pointer is near the boundary of the address space, and it also handles **negative indices** differently. LLVM keeps 64-bit indices to guarantee exact semantics.

(`nocapture` means this pointer is not stored anywhere else; `readonly` means memory is not written through it. Both are inferences made by clang.)

**Exercise 6.2** Hand-write an `.ll` defining `%struct.Pair = type { i64, i64 }`, and write a function `@get_second(ptr %p) -> i64` that returns the second field. Verify it with `llvm-as-18` and write a C driver test.

**Exercise 6.3** Explain the difference between the following two, and write a use case for each:
```llvm
%a = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1
%b = getelementptr inbounds %struct.Point, ptr %p, i64 1, i32 1
```

**Exercise 6.4** Write a function `int *advance(int *p, int n)` that returns `p + n`. Hand-write the IR and pay attention to the type conversion of the index.

**Exercise 6.5 (thinking question)** Why did LLVM design an instruction like `getelementptr` that "only computes addresses and does not access memory", instead of letting `load`/`store` carry an index directly? Hint: think about common subexpression elimination (CSE) and "address" as a first-class value.

**Exercise 6.6** Compile `static int hidden = 1; int pub = 2;` and observe the difference between `internal` and the default linkage. Use `nm` or `llvm-nm-18` to check symbol visibility.

## 6.7 Summary

- Global variables use `@`; `global` is writable, `constant` is read-only; `internal` is equivalent to C's `static` and `external` is equivalent to `extern`.
- `alloca` allocates on the stack and is released automatically when the function returns; there is no `free` in IR.
- **`getelementptr` only computes addresses and does not access memory.** Reading uses `load`, writing uses `store`.
- A GEP index is a count of **elements**, not bytes; `sizeof` is handled automatically by GEP.
- Structs need **two** indices: the first is the array step (usually 0), the second is the field number.
- `inbounds` is the promise of "not out of bounds"; the price is that going out of bounds is UB, and the benefit is more optimization.
- `sext` + `getelementptr` is the common pattern for a 32-bit index accessing a 64-bit address space.

In the next chapter we look at functions and calls.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 5 Control Flow: `br`, Basic Blocks and `phi`](05-ch05-control-flow-and-phi.md) · [Next: Chapter 7 Functions, Calling Conventions and Linkage →](07-ch07-functions-and-calls.md)
