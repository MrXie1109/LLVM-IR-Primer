# Chapter 17 Code Generation: Expressions, Variables and Calls

## 17.1 Refer back: "why variables live in memory" from Chapter 2

In Chapter 2 you saw the `-O0` `mul_add` for the first time, and there was a puzzle:

```llvm
%4 = alloca i32, align 4
%5 = alloca i32, align 4
%6 = alloca i32, align 4
store i32 %0, ptr %4, align 4
...
```

**Why are the parameters copied onto the stack?** The answer then was "to serve the debugger", and Chapter 14 added a second reason: "**trade memory for skipping dominator analysis**".

In this chapter you will **make that same choice yourself**, and you will see how large the payoff is: the whole of the variable-handling logic is only a few dozen lines, yet it handles `let`, `set`, loops and nested scopes correctly -- **because the hard problem of SSA construction has been outsourced to `mem2reg`**.

This chapter also covers a trap that is easy to fall into for real: **LLVM's numbering rules**. Chapter 8 gave a preview; here is the full post-mortem.

## 17.2 The overall structure of the compiler

```python
class Compiler:
    def __init__(self):
        self.module = Module()
        self.sigs = {}        # function name -> FunctionSig
        self.globals = {}     # global variable name -> (IR name, type)

    def compile_program(self, text):
        forms = read_all(text)
        # First pass: collect all signatures and global variables
        for form in forms:
            self.collect(form)
        # Second pass: generate function bodies
        for form in forms:
            self.emit_top(form)
        return self.module
```

**The two-pass scan is mandatory**, because of **forward references** and **recursion**:

```lisp
(defn outer (x) (inner (+ x 1)))     ; outer references inner, which is not defined yet
(defn inner (y) (* y 10))
```

With only one pass, `inner` does not exist yet when `outer` is compiled, and `compile_call` cannot find its signature.

The same reasoning applies to recursion:

```lisp
(defn fact (n) (if (<= n 1) 1 (* n (fact (- n 1)))))
```

`fact` references itself inside its own body -- if the body were compiled before the signature collection finished, `fact` would be undefined even to itself.

**This is the same problem as C's "declare before use"**, except that Lisp has no declaration syntax, so a two-pass scan takes its place.

## 17.3 Representing values

```python
class Value:
    """An SSA value: a named local variable, a constant, or a global."""
    __slots__ = ("ty", "name")

    def __init__(self, ty, name):
        self.ty = ty          # "i32" / "i1"
        self.name = name      # "%t1" / "42" / "@g"

    def __repr__(self):
        return f"Value({self.ty}, {self.name})"
```

**The key insight: `name` is just a string**, and it can be:

- `%t1` (an SSA temporary);
- `%n` (a parameter);
- `42` (a constant! note the absence of the `%` prefix);
- `@g_counter` (a global variable).

**Constants are also represented as `Value`**, which makes code generation very uniform:

```python
def compile_expr(self, fn, env, expr):
    if isinstance(expr, int):
        return Value(I32, str(expr))          # an integer constant is itself
```

So `(+ x 1)` generates `add i32 %x, 1` -- the second operand is literally `1`, and **no constant has to be "loaded" first**. This is exactly the "a constant can be an operand directly" point from Chapter 3.

## 17.4 Two representations for variables

This is the most important design decision in the chapter.

```python
class Var:
    """A Lisp variable: either an SSA value or a stack slot."""

    __slots__ = ("ir_name", "ty", "slot", "mutable")

    def __init__(self, ir_name, ty, slot, mutable=False):
        self.ir_name = ir_name
        self.ty = ty
        self.slot = slot
        self.mutable = mutable
```

The two forms:

| | `slot=False` (SSA value) | `slot=True` (stack slot) |
|---|---|---|
| Storage | an SSA name | an address produced by `alloca` |
| Read | use that name directly | generate a `load` |
| Write | **not allowed** | generate a `store` |
| Used for | function parameters | local variables bound by `let` |

**Why do parameters use SSA values?** Because a parameter **does not have to live on the stack under `-O0`** (even though clang puts it there). At function entry a parameter is fixed and immutable, so using its SSA name directly is simplest:

```llvm
define i32 @l_mul_add(i32 %x, i32 %y, i32 %z) {
entry0:
  %t1 = mul i32 %x, %y            ; <- use %x and %y directly
  %t2 = add i32 %t1, %z
  ret i32 %t2
}
```

**Why do `let` variables use stack slots?** Because they are **mutable** (`set` can modify them), and mutable things are awkward in SSA. This is what section 17.6 is about.

### Reading a variable

```python
def read_var(self, fn, var):
    """Turn a Var into an SSA Value at the current program point."""
    if var.slot:
        # Reading a stack slot is a load; the type is carried by the slot.
        return fn.emit_value(
            var.ty, f"load {var.ty}, ptr {var.ir_name}, align 4"
        )
    return Value(var.ty, var.ir_name)
```

Only 7 lines, but it unifies the two cases: wherever the variable lives, the caller gets a `Value`.

### Evaluating a symbol

```python
if isinstance(expr, Sym):
    var = env.lookup(expr.name)
    if var is not None:
        return self.read_var(fn, var)
    if expr.name in self.globals:
        ir_name, ty = self.globals[expr.name]
        return fn.emit_value(ty, f"load {ty}, ptr {ir_name}, align 4")
    raise IRError(f"unbound variable {expr.name!r}")
```

The lookup order is: **local variable -> global variable -> error**. A local variable shadows a global one, as in most languages.

### Scope

```python
class Frame:
    """A lexical scope: maps Lisp names to Var objects."""

    def __init__(self, parent=None):
        self.parent = parent
        self.vars = {}

    def lookup(self, name):
        frame = self
        while frame is not None:
            if name in frame.vars:
                return frame.vars[name]
            frame = frame.parent
        return None

    def define(self, name, var):
        self.vars[name] = var
```

A chained scope, where `lookup` walks up the parent chain. This corresponds to Lisp's lexical scoping rules.

## 17.5 Compiling `let`

```python
def op_let(self, fn, env, expr):
    """(let ((v e) ...) body...) -- introduce local variables.

    Every binding goes into a stack slot rather than an SSA register,
    because in this dialect `let` bindings are mutable (see `set`).
    Chapter 20 shows how `mem2reg` turns them back into registers.
    """
    if len(expr) < 3:
        raise IRError("let needs a binding list and a body")
    _, bindings, *body = expr
    if not isinstance(bindings, list):
        raise IRError("let bindings must be a list of pairs")

    inner = Frame(env)
    for pair in bindings:
        if not isinstance(pair, list) or len(pair) != 2:
            raise IRError(f"bad let binding {unparse(pair)}")
        name = pair[0]
        if not isinstance(name, Sym):
            raise IRError("let binding name must be a symbol")
        val = self.compile_expr(fn, inner, pair[1])
        slot = fn.alloca_slot(I32, hint=f"{name.name}")
        fn.emit(f"store i32 {val.name}, ptr {slot.name}, align 4")
        inner.define(name.name, Var(slot.name, I32, slot=True, mutable=True))

    result = Value(I32, "0")
    for form in body:
        result = self.compile_expr(fn, inner, form)
    return result
```

Three key points:

1. **A fresh `Frame(env)` is created** -- this is the implementation of lexical scope. Once the binding ends (the `let` body has been evaluated), the frame is discarded and the names naturally "go out of scope".
2. **Bindings are sequential**: `inner` is filled in step by step inside the loop, so a later binding can see an earlier one (as Chapter 15 promised).
3. **One `alloca` plus one `store` per binding**. The initial value is stored into the slot as soon as it has been computed.

Measured on `(let ((a 1) (b (+ a 1))) (+ a b))`:

```llvm
%a.addr = alloca i32, align 4
%b.addr = alloca i32, align 4
store i32 1, ptr %a.addr, align 4
%t1 = load i32, ptr %a.addr, align 4
%t2 = add i32 %t1, 1
store i32 %t2, ptr %b.addr, align 4
%t3 = load i32, ptr %a.addr, align 4
%t4 = load i32, ptr %b.addr, align 4
%t5 = add i32 %t3, %t4
ret i32 %t5
```

The initial value of `b` is indeed `load %a.addr` followed by `+1` -- **sequential binding is in effect**.

### The details of `alloca_slot`

```python
def alloca_slot(self, ty, hint="slot"):
    """Reserve a stack slot in the entry block and return its pointer."""
    name = f"%{hint}.addr"
    n = 1
    while any(name in a for a in self.entry_allocas):
        name = f"%{hint}.addr{n}"
        n += 1
    self.entry_allocas.append(f"  {name} = alloca {ty}, align {self._align(ty)}")
    return Value("ptr", name)
```

Two design points:

**First, the `alloca` is stored in `entry_allocas` and inserted at the start of the entry block at the end.** Chapter 6 noted that clang does the same. Why?

Because **if an `alloca` appears inside a loop body, every iteration allocates a fresh piece of stack space**, and the stack grows without bound. Hoisting every `alloca` into the entry block guarantees "allocated once, valid for the whole lifetime of the function". That is exactly the semantics of `alloca` -- its lifetime is function-wide.

**Second, name collisions are handled.** If the same `let` contains `(a 1)` and `(a 2)` (shadowing), or two different `let`s both bind `a`, their slot names collide. The `while` loop resolves this by appending a numeric suffix.

Measured on a shadowing example:

```lisp
(defn f (x)
  (let ((a 1))
    (let ((a 2))
      a)))
```

```llvm
%a.addr = alloca i32, align 4
%a.addr1 = alloca i32, align 4       ; ← the suffix resolves the collision
store i32 1, ptr %a.addr, align 4
store i32 2, ptr %a.addr1, align 4
%t1 = load i32, ptr %a.addr1, align 4   ; ← the inner binding shadows the outer one
ret i32 %t1
```

## 17.6 Compiling `set`: why memory is traded for SSA

```python
def op_set(self, fn, env, expr):
    """(set v e) -- assign to an existing local variable."""
    if len(expr) != 3:
        raise IRError("set takes a variable and a value")
    _, target, value_expr = expr
    if not isinstance(target, Sym):
        raise IRError("set target must be a symbol")
    var = env.lookup(target.name)
    if var is None:
        raise IRError(f"set of unbound variable {target.name!r}")
    if not var.slot:
        raise IRError(
            f"cannot assign to {target.name!r}: it is an SSA value, "
            "not a local slot"
        )
    val = self.compile_expr(fn, env, value_expr)
    fn.emit(f"store i32 {val.name}, ptr {var.ir_name}, align 4")
    return val
```

Note the `cannot assign to ... it is an SSA value` check: **a function parameter cannot be `set`**. This is not a defect but a deliberate restriction (as in many Lisp dialects), and it makes the error message clear.

Now the **core question**: if variables were not kept in memory, how would `set` be compiled?

Consider this loop:

```lisp
(let ((i 1) (s 0))
  (while (<= i n)
    (set s (+ s i))
    (set i (+ i 1)))
  s)
```

If `i` and `s` were SSA values, then "modifying" them inside the loop body would mean **producing new SSA names**:

```llvm
; hypothetical pure SSA version (needs phi)
while.cond:
  %i = phi i32 [ 1, %entry ], [ %i.next, %while.body ]
  %s = phi i32 [ 0, %entry ], [ %s.next, %while.body ]
  %c = icmp sle i32 %i, %n
  br i1 %c, label %while.body, label %while.end
while.body:
  %s.next = add i32 %s, %i
  %i.next = add i32 %i, 1
  br label %while.cond
```

**To produce that, the compiler would have to:**

1. know all predecessors of `while.cond` (so that the `phi` operands are right);
2. insert `phi` at the loop header;
3. feed the new values back from the end of the loop body into the `phi`.

Point 1 is hard for a **sequentially emitting** compiler -- when `while.cond` is emitted, the back edge from the loop body does not exist yet, so you **cannot know** whether the loop body will really jump back.

**That is why memory was chosen.** With `alloca`:

```llvm
while.cond1:
  %t1 = load i32, ptr %i.addr, align 4
  %t2 = icmp sle i32 %t1, %n
  br i1 %t2, label %while.body2, label %while.end3
while.body2:
  %t3 = load i32, ptr %s.addr, align 4
  %t4 = load i32, ptr %i.addr, align 4
  %t5 = add i32 %t3, %t4
  store i32 %t5, ptr %s.addr, align 4
  ...
  br label %while.cond1
```

**No `phi`, no dominator analysis, no predecessor information.** Every `load` reads "the current value in memory", and that value is **newly defined in the current block**, so it naturally dominates its own use.

**The cost** is the redundant reads and writes at run time. **But `mem2reg` removes them** (measured in Chapter 5 and Chapter 20). The result is a nice piece of engineering:

> **Redundant memory operations are traded for "the generator does not have to do dominator analysis", and then LLVM's `mem2reg` removes the redundancy for free.**

This is the **entire reason** the "bloated `-O0` IR" from Chapter 2 exists. clang does it, and so does this compiler.

### But the strategy is in fact a hybrid

The paragraph above can easily give the impression that "this compiler never needs `phi`". **That is wrong.** Before reading on, the real strategy has to be stated clearly, otherwise you will form an incorrect mental model of the generated IR.

This compiler uses **three different** representations for three kinds of things:

| Thing | Representation | Why |
|---|---|---|
| Function parameters | **SSA values** (`%x`) | immutable, used directly |
| Local variables bound by `let` | **stack slots** (`alloca`) | can be modified by `set` |
| **The value of `if`** | **a hand-emitted `phi`** | the predecessors of the two branches are **known**, so it can be written by hand |

Measured on this table (five functions of different shapes compiled with the same compiler):

```
alloca=0  phi=0   (defn f (x) x)                                          ; parameters only
alloca=0  phi=1   (defn f (x) (if (< x 0) 1 2))                           ; if only
alloca=1  phi=0   (defn f (x) (let ((y 1)) (+ x y)))                      ; let only
alloca=1  phi=0   (defn f (n) (let ((i 0)) (while (< i n) (set i (+ i 1))) i))  ; while only
alloca=1  phi=1   (defn f (x) (let ((y 1)) (if (< x 0) (set y 2) (set y 3)) y))  ; both
```

Therefore:

- `fib` has only parameters and `if` -> **zero `alloca`s but a `phi`** (the example in Chapter 19);
- `sum_to` has a `let` and a `while` -> **three `alloca`s and zero `phi`s** (the example in this chapter).

**Both shapes coexist, and both are correct.**

### Why `if` can emit `phi` by hand but `while` cannot

This is the key to understanding the whole trade-off:

**Both branches of an `if` have already finished by compile time**, so:
- the block the then branch ends up in is known (`then_end`, Chapter 18);
- the block the else branch ends up in is known;
- therefore `phi i32 [ then value, %then_end ], [ else value, %else_end ]` can be written **on the spot**.

**`while` cannot**, because the loop's back edge is a matter of the "future":
- when the `while.cond` block is compiled, the loop body **has not been generated yet**;
- so how many predecessors `while.cond` will have is unknown -- right now there is only the entry block, but an extra back edge from the end of the loop body is about to appear;
- emitting a `phi` at that moment would miss the predecessor that has not appeared yet, and **the verifier would report "PHI node entries do not match predecessors"** (the same family as the bug in Chapter 18).

**This is exactly the "sealed block" problem**: a block's `phi` can only be completed once all of its predecessors are fixed. The merge block of an `if` has its predecessors fixed after both branches are compiled; the cond block of a `while` has to wait until the loop body is compiled.

### So two different choices were made

| Case | Are the predecessors known? | What this compiler does |
|---|---|---|
| The merge of an `if` | **known at compile time** | emit a `phi` by hand |
| The cond of a `while` | **unknown at compile time** (the back edge appears later) | put the variables in stack slots, and **no `phi` is needed at all** |

**This division is not arbitrary; it corresponds exactly to "are the predecessors known".** Chapter 18 discusses this criterion in detail, along with the verifier error produced when it is handled incorrectly inside `op_if`.

> **The SSA machinery in `ir.py` also deserves a word.** The docstring of `ir.py` says it implements the sealed-block algorithm of Braun et al., "never needing to allocate stack slots". That machinery is **general and complete**, but it is **not used** in this pipeline (section 19.5 proves it with an instrumentation experiment). The reason is that actually putting it to use would require a whole bookkeeping scheme for "deferred completion of `phi`", and a simpler route was chosen -- **there is only one place that needs a `phi` (`if`), and writing three lines by hand is enough**.
>
> This is a real engineering phenomenon: **a framework offers more capability than the current requirement**. Section 19.5 honestly lists which code is live and which is idle.

## 17.7 Compiling a function

```python
def compile_function(self, form):
    _, name, params, *body = form
    param_names = [p.name for p in params]
    sig = self.sigs[name.name]
    fn = Function(
        sig.name,
        sig.ret_ty,
        sig.param_types,
        [f"%{p}" for p in param_names],
    )

    entry = fn.new_block("entry")
    fn.start(entry)

    env = Frame()
    for lisp_name, ir_name in zip(param_names, fn.param_names):
        env.define(lisp_name, Var(ir_name, I32, slot=False))

    # The body is an implicit (do ...): evaluate every expression, return the last.
    result = Value(I32, "0")
    for expr in body:
        result = self.compile_expr(fn, env, expr)
    fn.set_term(f"ret i32 {result.name}")
    fn.seal_block(entry)
    return fn
```

Three key points:

1. **Parameters are bound as SSA values** (`slot=False`), using names such as `%x` and `%y` directly.
2. **`entry` has a name** (as Chapter 8 explained: named blocks do not consume numbers).
3. **The function body is an implicit `do`**: evaluate in order, return the value of the last expression.

Measured:

```lisp
(defn mul_add (x y z) (+ (* x y) z))
```

```llvm
define i32 @l_mul_add(i32 %x, i32 %y, i32 %z) {
entry0:
  %t1 = mul i32 %x, %y
  %t2 = add i32 %t1, %z
  ret i32 %t2
}
```

**Only 3 instructions, and no `alloca`.** Compare that with the 12 instructions of clang `-O0` in Chapter 2 -- here the compiler generates code closer to `-O2`, because the parameters are SSA values directly and there are no mutable local variables.

(Note in passing that the block name is `entry0` rather than `entry`. That is because `new_block("entry")` appends a counter suffix to the label to avoid collisions. It is an implementation detail of `ir.py`.)

## 17.8 Compiling a call

```python
def compile_call(self, fn, env, expr):
    head = expr[0].name
    sig = self.sigs[head]
    args = [self.compile_expr(fn, env, a) for a in expr[1:]]
    if len(args) != len(sig.param_types):
        raise IRError(
            f"{head} expects {len(sig.param_types)} arguments, "
            f"got {len(args)}"
        )
    arg_text = ", ".join(
        f"{ty} {a.name}" for ty, a in zip(sig.param_types, args)
    )
    return fn.emit_value(
        sig.ret_ty, f"call {sig.ret_ty} @{sig.name}({arg_text})"
    )
```

Note **`@{sig.name}`**, not `@{head}`. This is **name mangling**:

```python
SYMBOL_PREFIX = "l_"

def mangle(name):
    return SYMBOL_PREFIX + name
```

### Why the symbols must be mangled

Lisp lets you write:

```lisp
(defn double (x) (* x 2))
(defn abs (x) (if (< x 0) (- 0 x) x))
```

But `double` is a C keyword, and `abs` is a function from `<stdlib.h>`! If the Lisp names were used directly as IR symbol names, **the generated module could not be linked with C code**:

```
error: cannot combine with previous 'int' declaration specifier
    int double(int);
        ^
```

A C driver that declares `int double(int);` outright fails to compile immediately:

After adding the `l_` prefix:

```llvm
define i32 @l_double(i32 %x) { ... }
define i32 @l_abs(i32 %x) { ... }
```

**The collision is gone.** Every real compiler has to do this -- C++'s Itanium ABI mangling, Rust's legacy/`v0` mangling are essentially the same problem: **the source language's namespace and the object file's namespace differ, so a mapping is needed.**

(The `l_` prefix here is extremely simple and encodes no types, so overloading is not supported. For this language that is enough. The C++ scheme that mangles `void f(int)` into `_Z1fi` exists to support overloading and namespaces -- features this language does not have.)

## 17.9 That real trap: numbered values

Now for the trap that Chapter 8 previewed. It is easy to fall into, and the error message afterwards is hard to understand.

### The naive implementation

```python
class Function:
    def __init__(self):
        self.temp_counter = 0

    def new_temp(self):
        self.temp_counter += 1
        return f"%{self.temp_counter}"        # ← numbered values
```

The generator's idea is: "I count them myself, the first temporary is `%1`, the second is `%2`..."

**This fails.** As Chapter 8 explained, LLVM's numbered counter is **shared by parameters, anonymous basic blocks, and instructions that produce a result**. And the generator inserts a lot of basic blocks while generating:

```python
then_block = fn.new_block("then")     # the generator thinks this is just a name
```

In `ir.py`, `new_block` uses **named labels** (`then1`, `else2`), so they consume no numbers. **But if the generator used numbered labels, or used `%{counter}` for temporaries, the counter would drift out of step with LLVM's real counter.**

### The real error

The error looks like this:

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
  %4 = sub i32 %m, 1        ; ← numbering goes backwards from %6 to %4
  ret i32 %4
}
```

```bash
$ llvm-as-18 numfail.ll -o /dev/null
llvm-as-18: numfail.ll:8:1: error: label expected to be numbered '7' or greater
3:
^
```

(Source file: `code/part2-ir/numfail.ll`.)

What that means: the generator thought "the next number is `%4`", but LLVM's counter had already climbed to 12.

### Why this bug is especially hard to track down

Because it **does not report an error every time**. Back to the rule from Chapter 8:

> **Numbered values must increase monotonically, but gaps are allowed.**

So when the generator's counter is **too small** it errors (as above), but when it is **too large** there is **no error**:

```llvm
define i32 @f(i32 %x) {
entry:
  %5 = add i32 %x, 1       ; skips %1..%4, LLVM accepts it
  ret i32 %5
}
```

**This passes verification.** But the problem is that the numbering is now out of step with the actual structure: if you later want to insert an instruction somewhere, you find that "no number is available" -- because larger numbers already exist both before and after it.

**Worse still**: if the generator mixes numbered labels with named labels, some functions pass and some do not, and the reported error location points at a place you never wrote.

### The solution: use named values throughout

This was already done in Chapter 14:

```python
def new_temp(self):
    """Allocate a new *named* temporary."""
    self.temp_counter += 1
    return f"%t{self.temp_counter}"
```

which generates:

```llvm
define i32 @l_fib(i32 %n) {
entry0:
  %t1 = icmp slt i32 %n, 2
  br i1 %t1, label %then1, label %else2
```

**The parameters are named, the temporaries are named, the block labels are named -- there are no numbered values at all, and the rule simply does not apply.**

### The lesson of this trap

> **Do not deal with implicit rules you do not fully understand.**

Time could be spent precisely simulating LLVM's numbering rules (which instructions consume a number, how anonymous blocks affect the counter), but that is an **unnecessary** burden. Named values are a few characters longer, and in exchange:

- it is impossible to fail because the counter drifted;
- the generated IR is more readable (`%t1` is more meaningful than `%7` -- at least it clearly marks "this is my temporary");
- when debugging, you can see at a glance which value was generated by what.

**This is not "bypassing" the rule, but an engineering choice made after understanding it.**

## 17.10 Exercises

**Exercise 17.1** Compile `(defn f (x) (let ((y 1)) (set y 2) y))` and look at the generated IR. Count how many `alloca`s, `load`s and `store`s there are. Then run `mem2reg` and watch them disappear.

**Exercise 17.2** Try assigning to a function parameter:

```lisp
(defn f (x) (set x 5))
```

Record the error message. Then modify the compiler so that parameters can be `set` too (hint: set the parameter's `slot` to `True` and generate an `alloca` + `store` for it). Roughly how many lines does that change take?

**Exercise 17.3** Compile `(defn f (x) (mul_add x x x))`, where `mul_add` is defined elsewhere. Look at how arguments are passed to the `call` instruction.

**Exercise 17.4** Remove the `l_` prefix from `mangle`, then link the generated IR with a C driver that contains `double`. Record the error. Then restore the prefix.

**Exercise 17.5** Deliberately change `new_temp` back to the numbered-value version:

```python
def new_temp(self):
    self.temp_counter += 1
    return f"%{self.temp_counter}"
```

Compile a function containing an `if`, verify it with `llvm-as-18`, and record the complete error message. Then think about why some functions pass and others do not.

**Exercise 17.6 (thought question)** `read_var` returns a `Value` for both SSA values and stack slots. What is the benefit of that "uniform interface"? If parameters also used stack slots, would the code become simpler or more complex?

## 17.11 Summary

- Compilation is split into two passes: **collect all signatures first, then generate function bodies** -- for forward references and recursion.
- Constants are also represented as `Value` (the name is the number itself), so operands are uniform.
- Variables have two representations: **parameters use SSA values** (immutable), **`let` variables use stack slots** (mutable).
- **`let` variables are put in memory to support `set`** -- a pure SSA `set` would require inserting a `phi` at a loop header whose predecessors are unknown, which is infeasible for a sequentially emitting compiler.
- **`alloca` is hoisted into the entry block**, because its lifetime is function-wide; leaving it inside a loop would make the stack grow without bound.
- **The `l_` name mangling is mandatory**: Lisp names would collide with C's `double`, `abs`, and so on.
- **Do not generate IR with numbered values.** The numbered counter is shared by "parameters + anonymous blocks + instructions with results", simulating it costs far more than it gains, and the legality of gaps makes errors hard to spot. Use named values such as `%t1`.

The next chapter moves on to the hardest part: control flow and `phi`.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 16 Lexing and Parsing](16-ch16-lexing-and-parsing.md) · [Next: Chapter 18 Control Flow and `phi` Nodes →](18-ch18-control-flow-and-phi-nodes.md)
