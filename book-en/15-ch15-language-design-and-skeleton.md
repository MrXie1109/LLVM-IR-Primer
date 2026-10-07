# Chapter 15 Language Design and Project Skeleton

## 15.1 Referring Back: That 100-Line Skeleton from Chapter 14

In Chapter 14 we wrote this:

```python
def generate_add():
    fn = Function("add", "i32", ["i32", "i32"], ["%a", "%b"])
    entry = fn.new_block("entry")
    fn.start(entry)
    r = fn.emit_value("i32", "add i32 %a, %b")
    fn.terminate(f"ret i32 {r}")
    return fn.render()
```

It generates a piece of IR that passes verification by `llvm-as-18`, can be executed by `lli-18`, and computes 42.

**The task of this chapter is to answer one design question**: to grow those 100 lines into a real compiler, what trade-offs must we make?

Because a compiler can be infinitely complex. Without clear boundaries, Part III would become a thousand-page tome on compiler theory, whereas what you want to learn is **LLVM IR**. So the most important section of this chapter is **15.3: what we do NOT do**.

## 15.2 Why Lisp

The source language of this book is a Lisp dialect. The reasons are concrete:

**Reason one: the syntax of S-expressions can be explained in an hour.**

Our complete grammar takes one page (Section 15.4). If the source language were a subset of C, Chapter 16 would spend dozens of pages on type declarations, operator precedence, and how to read pointer declarators (what on earth is `int (*f)(int)`?), and **none of that has anything to do with LLVM IR**.

**Reason two: S-expressions make the "syntax tree" and the "source code" almost isomorphic.**

```lisp
(+ (* x y) z)
```

Once read into memory this is `[Sym(+), [Sym(*), Sym(x), Sym(y)], Sym(z)]` — a nested list. You do not need to design AST node classes, and you do not need the Visitor pattern. The whole of Chapter 16 can be compressed into something very short.

**Reason three: Lisp is expressive enough to write real test programs.**

We can write recursion (`fib`), loops (`sum_to`), and mutual recursion (`even?`/`odd?`). These are enough to cover every difficulty of IR generation: `br`, `phi`, `alloca`, `call`.

**Reason four: Lisp and SSA share a deep characteristic — both are "value-oriented".**

Every expression in Lisp **produces a value**; every instruction in SSA **produces a value** as well. This consistency makes "compiling an expression" natural: compile an expression, and return a `Value`.

## 15.3 What We Implement and What We Do Not

This is the most important section of the chapter. **An honest design document starts by stating its boundaries.**

### What We Implement

| Feature | Syntax | Corresponding IR |
|---|---|---|
| Function definition | `(defn name (params...) body...)` | `define` |
| External function declaration | `(declare name (params...))` | `declare` |
| Global variable | `(defg name init)` | `@name = global i32 init` |
| Local binding | `(let ((v e)...) body...)` | `alloca` + `store` |
| Assignment | `(set v e)` | `store` |
| Condition | `(if cond then else)` | `br` + `phi` |
| Loop | `(while cond body...)` | `br` + back edge |
| Arithmetic | `(+ - * / %)` | `add`, `sub`, `mul`, `sdiv`, `srem` |
| Comparison | `(< <= > >= = !=)` | `icmp` |
| Function call | `(f args...)` | `call` |
| Integer constant | `42`, `-7` | `i32 42` |
| Comment | `;` to end of line | none (discarded at compile time) |

### What We Do NOT Implement — and Why

This list is just as important as the one above.

#### 1. No closures

```lisp
; we do not support this
(defn make_adder (n)
  (fn (x) (+ x n)))      ; ← the inner function captures n
```

**Why not?** A closure needs a **heap-allocated environment record**:

```llvm
%env = call ptr @malloc(i64 8)      ; allocate the environment
store i32 %n, ptr %env              ; store n into it
; then every inner function must take a %env parameter
```

That drags in `malloc`, the design of a memory layout, and "who is responsible for freeing". These are problems of the **runtime system**, not problems of **IR generation**. Every chapter of this book should serve the goal of "understanding IR", and closures would make us spend three chapters on memory management.

**The cost**: we can only use top-level functions and recursion; we cannot do higher-order functions.

#### 2. Only Top-Level Functions, No Nested Functions

```lisp
(defn outer (x)
  (defn inner (y) ...)    ; ← defining a function inside a function is not supported
  ...)
```

**Why?** Without closures, nested functions amount to nothing more than "nested scopes", which is of little value; and once you support them you have to deal with name capture and the `internal` linkage. **Small payoff, high cost.**

**The cost**: all functions are top-level and globally visible.

#### 3. No Dynamic Typing

The Lisp family traditionally has dynamic typing: a variable can be an integer first and a string later. **We do not do that.**

Our rule is:

> **Every expression produces `i32`; comparisons produce `i1` (but are promoted automatically).**

**Why?** A single static type gives the "compile an expression" function a **deterministic return type**:

```python
def compile_expr(self, fn, env, expr) -> Value:
    """Compile an expression and return an SSA value of type i32."""
```

If we wanted dynamic typing, every value would have to be a "tagged union":

```llvm
%value = type { i32, i64 }    ; { tag, payload }
```

and then every operation would have to check the tag first and call into runtime error handling on failure. That would drown the logic of IR generation.

**The cost**: no strings, no lists, no floating point. Only `i32`.

#### 4. No Garbage Collection, Memory Leaks Are Allowed

Our compiler **produces no heap allocation at all**.

- All local variables are on the stack (`alloca`), and are released automatically when the function returns;
- There are no calls to `malloc`/`free`;
- Therefore **memory leaks are impossible** — because we have no heap at all.

**Wait, so what does "allowing leaks" even mean here?** To be clear: if we did implement closures or lists (which need `malloc`), we would **deliberately not do reference counting and not do GC**, and simply let memory leak. Because memory management is the job of a runtime library, and cramming it into an IR textbook would only be a distraction.

**The cost**: the language can only express problems that "can be computed to completion on the stack" — but that happens to cover every IR feature we want to demonstrate.

#### 5. No Tail-Call Optimization

```lisp
(defn count_down (n)
  (if (= n 0)
      0
      (count_down (- n 1))))    ; ← this is a tail call
```

The Scheme standard requires that tail calls consume no stack space. **Our compiler does not perform this optimization**, so the function above will overflow the stack when `n` is large.

**Why not?** Tail-call optimization requires **identifying tail positions at compile time** and rewriting `call` + `ret` into a `musttail call` or a loop. That is a **function-level** transformation, whereas our compiler is **expression-level** — it does not look back at instructions it has already generated.

**But there is good news here**: LLVM does tail-call optimization itself. If you run `-O2` on the IR we generate, the `tailcallelim` pass will try to turn the tail recursion into a loop. So **we have delegated this job to LLVM** — which is precisely where the value of the "write your own front end + reuse the LLVM back end" architecture lies.

**This trade-off can be verified experimentally**, and the result is quite convincing. Consider a tail-recursive accumulator function:

```lisp
(defn sum_acc (n acc)
  (if (= n 0)
      acc
      (sum_acc (- n 1) (+ acc n))))
```

The `-O0` IR our compiler generates:

```llvm
define i32 @l_sum_acc(i32 %n, i32 %acc) {
entry0:
  %t1 = icmp eq i32 %n, 0
  br i1 %t1, label %then1, label %else2
then1:
  br label %merge3
else2:
  %t2 = sub i32 %n, 1
  %t3 = add i32 %acc, %n
  %t4 = call i32 @l_sum_acc(i32 %t2, i32 %t3)
  br label %merge3
merge3:
  %t5 = phi i32 [ %acc, %then1 ], [ %t4, %else2 ]
  ret i32 %t5
}
```

Notice that `%t4 = call i32 @l_sum_acc(...)` is immediately followed by `br label %merge3`, and `merge3` does nothing but `ret`. **This is a tail call**, but our compiler cannot see it — it dutifully generates a real `call`, and stack frames accumulate one after another.

Measure it (using a C driver to call it):

```bash
$ clang-18 -w driver.c ta.bc -o ta0 && ./ta0
sum_acc(100,0)=5050
$ echo $?          # with only a small argument this is normal
0
```

But change the argument to one million:

```
$ ./ta0            # with l_sum_acc(1000000, 0)
Segmentation fault  # exit=139
```

**Segmentation fault.** Because we do not do tail-call optimization, one million stack frames blow up the stack.

Now hand the same IR to LLVM's `-O2`:

```bash
$ opt-18 -passes='default<O2>' -S ta.ll -o ta_o2.ll
```

```llvm
define i32 @l_sum_acc(i32 %n, i32 %acc) local_unnamed_addr #0 {
entry0:
  %t11 = icmp eq i32 %n, 0
  br i1 %t11, label %merge3, label %else2.preheader

else2.preheader:                                  ; preds = %entry0
  %0 = add i32 %n, -1
  %1 = mul i32 %0, %0
  %2 = zext i32 %0 to i33
  %3 = add i32 %n, -2
  %4 = zext i32 %3 to i33
  %5 = mul i33 %2, %4
  %6 = lshr i33 %5, 1
  %7 = trunc i33 %6 to i32
  %8 = add i32 %acc, %n
  %9 = add i32 %8, %1
  %10 = sub i32 %9, %7
  br label %merge3

merge3:                                           ; preds = %else2.preheader, %entry0
  %acc.tr.lcssa = phi i32 [ %acc, %entry0 ], [ %10, %else2.preheader ]
  ret i32 %acc.tr.lcssa
}
```

**The `call` is gone.** The recursion has been eliminated entirely: `tailcallelim` turned it into a loop, and then `loop-idiom` and `indvars` turned the loop into a closed-form formula (note those `i33`s — again the overflow-safe intermediate type from Chapter 11).

And notice that variable name, **`%acc.tr.lcssa`** — `tr` is short for tail-recursion, and `lcssa` is **L**oop-**C**losed **S**SA **A**form. The name of an SSA variable leaks the optimizer's processing history.

Run it:

```
$ ./tao2
sum_acc(100,0)=5050 (expect 5050)
sum_acc(1000000,0)=1784293664 (expect 1784293664)
```

**Correct, and no longer crashing.** Two pieces of IR from the same front end go from "segmentation fault" to "exactly the right result" after LLVM optimization.

> **This experiment is the central argument of Part III of this book**: your front end does not need to do everything. **Translate semantics into IR faithfully and clumsily, then let LLVM do the optimizing** — this is the most important division of labour in modern compiler architecture. The work you save is exactly the reason LLVM exists.

**The cost**: if you do **not** run the optimizer (as with `-O0`), deep recursion will overflow the stack. This is a limitation users need to know about.

#### 6. No Type Inference, No Macros, No Multiple Return Values, No Exceptions

These either require a type system or require runtime support. **None of them are done.**

### What This Subtraction Buys

After all the subtraction, our language has:

- **One type** (`i32`, plus `i1` used internally);
- **Nine special forms/operators** (`defn`, `defg`, `declare`, `let`, `set`, `if`, `while`, plus arithmetic and comparison);
- **About 500 lines of code generator**.

**But its output is real LLVM IR, accepted by LLVM's verifier, optimized by LLVM's optimizer, and compiled to machine code by LLVM's back end.** That is enough — because what this book teaches is IR, not "how to write a complete Scheme".

> **Advice for the reader**: if you want to extend it after finishing the book, the three features most worth adding, in order of difficulty, are:
> 1. **Floating-point support** (add a `double` type and `fadd`/`fmul`/`fcmp`) — mainly a matter of replacing `i32` with a type variable;
> 2. **Arrays and pointers** (add `getelementptr`) — this requires introducing the notion of an "lvalue";
> 3. **Closures** — this needs heap allocation and function pointers, and amounts to roughly a rewrite.
>
> Adding items 1 and 2 lets you generate by hand all the IR you learned in Part I, and gives the best value for effort.

## 15.4 The Complete Grammar of the Language

This is the complete grammar definition. It is only one page.

```
program     ::= form*
form        ::= "(" defn ")" | "(" defg ")" | "(" declare ")" | expr

defn        ::= "defn" symbol "(" symbol* ")" expr+
defg        ::= "defg" symbol integer
declare     ::= "declare" symbol "(" type* ")"
type        ::= "i32"

expr        ::= integer
              | symbol
              | "(" let ")" | "(" set ")" | "(" if ")" | "(" while ")"
              | "(" op expr expr ")" | "(" call ")"

let         ::= "let" "(" "(" symbol expr ")" * ")" expr+
set         ::= "set" symbol expr
if          ::= "if" expr expr expr
while       ::= "while" expr expr*

op          ::= "+" | "-" | "*" | "/" | "%"
              | "<" | "<=" | ">" | ">=" | "=" | "!="

call        ::= symbol expr*
```

### Semantic Points

**Every expression has a value.** `if` has a value (the values of the two branches are merged), `let` has a value (the value of the last body expression), and the value of `while` is `0`.

**A function body is an implicit `do`.** `(defn f (x) e1 e2 e3)` evaluates them in order and returns `e3`.

**The bindings of `let` are sequential**, and later bindings can see earlier ones:

```lisp
(let ((a 1) (b (+ a 1)))    ; b can see a
  (+ a b))                   ; => 3
```

(This is not a question of the difference between `let*` and `let` — we have only one `let`, and it is sequential.)

**`if` must have an else branch.** Because we have no `void` type, `if` must produce an `i32`. To express the side effect of "then branch only", use `(if c e 0)`.

**The value of `while` is `0`.** It has side effects (modifying local variables through `set`), but it itself produces `i32 0` in order to keep the consistency of "every expression has a value".

**A comparison returns `i1`, but is promoted automatically.** When the result of a comparison is used as an arithmetic operand (for example `(+ (< a b) 1)`), the compiler inserts a `zext` automatically:

```python
def to_i1(self, fn, val):
    """Reduce a value to i1, because br needs i1."""
```

### A Complete Example

```lisp
; sum 1 to n
(defn sum_to (n)
  (let ((i 1) (s 0))
    (while (<= i n)
      (set s (+ s i))
      (set i (+ i 1)))
    s))

; recursive factorial
(defn fact (n)
  (if (<= n 1)
      1
      (* n (fact (- n 1)))))

; declare an external C function and use it
(declare ext_abs (i32))
(defn abs_via_c (x) (ext_abs x))
```

## 15.5 The Project Skeleton

```
code/part3-lispc/
├── lexer.py       lexing: text -> token stream
├── reader.py      parsing: token stream -> S-expressions
├── ir.py          the LLVM IR builder: insertion point, basic blocks, SSA variables
├── compiler.py    code generation: S-expressions -> IR
├── tests.py       end-to-end tests (22 cases)
└── examples/
    ├── fib.lisp        recursive Fibonacci
    ├── sum.lisp        while loop + mutable variables
    ├── countdown.lisp  tail recursion (tests whether LLVM can eliminate the tail call)
    └── tailacc.lisp    tail recursion with an accumulator
```

**The dependencies run in one direction only**, with no circular imports:

```
lexer.py  ←  reader.py  ←  compiler.py  →  ir.py
```

| File | Lines | Responsibility |
|---|---|---|
| `lexer.py` | ~100 | Cut the text into tokens, tracking line and column numbers |
| `reader.py` | ~130 | Assemble tokens into nested lists, distinguishing symbols from integers |
| `ir.py` | ~430 | The IR builder: `Block`, `Function`, `Module`; it also contains an **unused** general SSA construction mechanism (see Section 19.5) |
| `compiler.py` | ~490 | Code generation: dispatch to the various `op_*` methods |
| `tests.py` | ~400 | End-to-end tests |

**Why separate `ir.py` and `compiler.py`?**

Because they are **two different concerns**:

- `ir.py` cares about "how to organise IR into a renderable structure"; it does not know that Lisp exists;
- `compiler.py` cares about "how each Lisp construct should be translated"; it calls the API of `ir.py`.

The practical benefit of this layering is that **`ir.py` can be reused to compile other languages**. If you wanted to add a C-subset front end to this book, not a single line of `ir.py` would need to change.

**This is also LLVM's own architecture**: the front end (clang) and the back end (LLVM Core) communicate only through IR. We imitate that design at a small scale.

## 15.6 Division of Labour Between Chapters

| Chapter | Content | Corresponding files |
|---|---|---|
| Chapter 15 | Design decisions and the skeleton (this chapter) | — |
| Chapter 16 | Lexing, parsing, error reporting | `lexer.py`, `reader.py` |
| Chapter 17 | Expressions, variables, calls, `alloca`/`mem2reg` | `ir.py`, `compiler.py` (in part) |
| Chapter 18 | Control flow, `phi`, that real bug | `compiler.py` (`op_if`, `op_while`) |
| Chapter 19 | A complete code walkthrough | everything |
| Chapter 20 | Testing, verification, optimization | `tests.py` |

## 15.7 Exercises

**Exercise 15.1** Pick one feature from the "not implemented" list in Section 15.3 and write down: (a) what new instructions it would require in IR, (b) what the runtime library would have to provide, (c) roughly how much code it would take. **The purpose of this exercise is to let you experience that "language design is trade-offs".**

**Exercise 15.2** Using the skeleton from Chapter 14, write the generating code for `(defn square (x) (* x x))` (no parser needed; just write the Python calls directly). Verify the generated IR.

**Exercise 15.3** Our language has no `else if`. Using nested `if`, write a function that decides whether an integer is positive, negative or zero, and then think about this: why is no `else if` syntactic sugar needed? (Hint: `if` is an **expression**, and can be nested in the else position.)

**Exercise 15.4** Our `while` returns `0`. Design a counterexample that shows what trouble a "`while` with a return value" would cause (hint: the loop may execute 0 times, so what should the return value be in that case?).

**Exercise 15.5 (discussion)** Why do we split `lexer`/`reader` and `ir`/`compiler` into four files instead of writing one 1000-line script? Hint: think about the `expected instruction opcode` error from Chapter 14 — if parsing and code generation were mixed together, how would you go about locating an error?

## 15.8 Summary

- Lisp was chosen because its syntax can be explained on one page, letting you put all your effort into IR generation.
- **An explicit "not doing" list is just as important as the feature list**: no closures, no nested functions, no dynamic typing, no GC, no tail-call optimization.
- These subtractions give us a code generator of about 500 lines, **but its output is real IR that LLVM can verify and optimize**.
- The language has only one type, `i32` (plus `i1` internally); every expression produces a value.
- The project has four layers: `lexer` → `reader` → `compiler` → `ir`, with one-directional dependencies.
- `ir.py` has nothing to do with Lisp and can be reused — this is precisely a small-scale embodiment of LLVM's idea that "front end and back end communicate through IR".

In the next chapter we write the lexer and the parser.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 14 From Reading IR to Writing IR: Build Order and Lifetime](14-ch14-from-reading-to-writing-ir.md) · [Next: Chapter 16 Lexing and Parsing →](16-ch16-lexing-and-parsing.md)
