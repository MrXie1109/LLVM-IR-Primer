# Chapter 19 A Complete Code Walkthrough

## 19.1 Refer back: this chapter ties all the previous ones together

The previous four chapters covered, respectively:

| Chapter | Content |
|---|---|
| Chapter 15 | Design decisions and the "do-not-do list" |
| Chapter 16 | Lexing and parsing |
| Chapter 17 | Expressions, variables, calls, and the trade-offs of `alloca` |
| Chapter 18 | Control flow and `phi`, plus that real bug |

**This chapter introduces no new concepts.** Its job is to string these fragments into a complete, runnable whole, and to state honestly: **which code is "live" and which is standby machinery.**

Chapter 15 said:

> The project has four layers: `lexer` -> `reader` -> `compiler` -> `ir`, with one-way dependencies.

This chapter verifies that the architecture really holds.

## 19.2 The full picture

```
                     source text
                        │
        ┌──────────────┴──────────────┐
        │  lexer.py                    │  characters → tokens
        │  tokenize(text) -> [Token]   │
        └──────────────┬──────────────┘
                        │  token stream
        ┌──────────────┴──────────────┐
        │  reader.py                   │  tokens → S-expressions
        │  read_all(text) -> [list]    │
        └──────────────┬──────────────┘
                        │  S-expressions (Python list / int / Sym)
        ┌──────────────┴──────────────┐
        │  compiler.py                 │  S-expressions → IR
        │  Compiler.compile_program()  │
        │    ├─ collect()   first pass: signatures │
        │    └─ emit_top()  second pass: bodies    │
        └──────────────┬──────────────┘
                        │  calls into the ir.py API
        ┌──────────────┴──────────────┐
        │  ir.py                       │  IR structures → text
        │  Module / Function / Block   │
        │  Value / Phi                 │
        └──────────────┬──────────────┘
                        │
                   LLVM IR text
```

**Note that `ir.py` sits at the bottom of the diagram and does not know that Lisp exists.** That is the layering Chapter 15 emphasized.

Be careful with the wording when verifying this, because Python has a `while` keyword of its own and some of these words also occur in docstrings. A more precise check is "does it contain any construct names specific to Lisp":

```bash
$ grep -n '"defn"\|"let"\|"set"\|"if"\|"while"\|Sym\|read_all' ir.py
(no output)
```

**No matches at all.** The occurrences of `while` in `ir.py` (lines 152, 220, 342 and so on) are all **Python `while` statements**, and `let` appears in English comments ("let the block body be filled in later") -- neither is a reference to Lisp.

The only trace is the default name in `Module.__init__`:

```python
def __init__(self, name="lisp_module"):
```

That is an inconsequential default string, and the compiler never uses it when rendering.

**The conclusion holds**: `ir.py` does not depend on the source language and can be reused by any front end.

## 19.3 Structural inventory of each module

### `ir.py`: the IR builder

```
IRError                 exception
Value(ty, name)         SSA value (may be a constant!)
Phi(ty, name, block)    an incomplete phi node
Block(label)            basic block
  add(text)             append an instruction (forbidden after termination)
  terminate(text)       set the terminator
  render(prefix)        render to text

Function(name, ret_ty, param_types, param_names)
  new_block(hint)       create a block
  start(block)          move the insertion point
  reserve_block(hint)   reserve a label (Chapter 18)
  branch_placeholder()  branch to a reserved block
  realize(placeholder)  turn a reserved block into a real block
  new_temp()            allocate a named temporary %tN
  emit(text)            emit an instruction
  emit_value(ty, text)  emit an instruction that produces a value
  set_term(text)        set the terminator
  branch(target)        unconditional branch
  cond_branch(c,t,e)    conditional branch
  alloca_slot(ty, hint) allocate a stack slot in the entry block
  var(name, ty)         read a variable (SSA construction)
  set_var(name, ty, v)  write a variable
  seal_block(block)     seal a block (complete phis)
  materialize_phis()    insert phis at the start of blocks
  render()              render the whole function

Module(name)
  add_global / declare / add_function / render
```

### `compiler.py`: code generation

```
Var(ir_name, ty, slot, mutable)       variable (SSA value or stack slot)
Frame(parent)                         lexical scope chain
FunctionSig(name, ret_ty, param_types) function signature

SYMBOL_PREFIX = "l_"                  name mangling prefix
mangle(name)                          Lisp name → IR symbol name
OPERATOR_METHODS                      operator → method name dictionary

Compiler
  compile_program(text)   entry point: two-pass scan
  collect(form)           first pass: collect signatures
  emit_top(form)          second pass: generate
  compile_function(form)  compile one function
  compile_expr(fn, env, e) core dispatch
  read_var(fn, var)       read a variable
  op_let / op_set / op_if / op_while   special forms
  compile_call            function call
  _binary + op_add..op_ne arithmetic and comparison
  to_i1(fn, val)          reduce to i1

compile_text(text)      convenience entry point
main(argv)              command-line entry point
```

### The operator dispatch table

Chapter 17 mentioned `OPERATOR_METHODS`; here is its full contents:

```python
OPERATOR_METHODS = {
    "let": "op_let",
    "if": "op_if",
    "while": "op_while",
    "set": "op_set",
    "+": "op_add",
    "-": "op_sub",
    "*": "op_mul",
    "/": "op_div",
    "%": "op_mod",
    "<": "op_lt",
    "<=": "op_le",
    ">": "op_gt",
    ">=": "op_ge",
    "=": "op_eq",
    "==": "op_eq",
    "!=": "op_ne",
}
```

**Why use an explicit table instead of mechanically turning symbol names into method names?**

There is a seemingly "cleverer" approach: mechanically build the method name from the symbol name:

```python
handler = getattr(self, f"op_{head.name.replace('-', '_')}", None)
```

Then `read_one('(< a b)')` fails to compile:

```
IRError: unknown operator or function '<'
```

**The reason**: `<` would turn into `op_<`, and `op_<` **is not a legal Python identifier**. The same problem occurs for `=`, `/`, `*` and `+` (these symbols cannot appear in a Python name).

The lesson:

> **The set of identifiers in the source language differs from the set of identifiers in the target language, so an explicit mapping is needed in between.**

This is the same class of problem as `mangle`, at two different levels:

- `mangle` solves "Lisp function name -> IR symbol name";
- `OPERATOR_METHODS` solves "Lisp operator name -> Python method name".

## 19.4 The complete flow: compiling `fib`

A real example, from beginning to end.

### Step 0: the source

```lisp
; Recursive Fibonacci: the classic first LLVM IR program.
(defn fib (n)
  (if (< n 2)
      n
      (+ (fib (- n 1)) (fib (- n 2)))))
```

### Step 1: lexing

```python
>>> from lexer import tokenize
>>> toks = tokenize(open('examples/fib.lisp').read())
>>> [(t.kind, t.value) for t in toks[:12]]
[('punct', '('), ('sym', 'defn'), ('sym', 'fib'), ('punct', '('),
 ('sym', 'n'), ('punct', ')'), ('punct', '('), ('sym', 'if'),
 ('punct', '('), ('sym', '<'), ('sym', 'n'), ('int', 2)]
```

**Note that the `;` comment line produces no tokens at all** -- the lexer skips it.

Note also how `-` is handled: in `(- n 1)` the `-` is followed by a space, so it is a symbol; `-3` is recognized as an integer (Chapter 16).

### Step 2: parsing

```python
>>> from reader import read_all
>>> forms = read_all(open('examples/fib.lisp').read())
>>> forms[0]
[defn, fib, [n], [if, [<, n, 2], n, [+, [fib, [-, n, 1]], [fib, [-, n, 2]]]]]
```

A nested list. `defn`, `fib`, `n`, `if` and so on are `Sym` objects; `2` and `1` are Python `int`s.

### Step 3: the first pass (collecting signatures)

```python
>>> from compiler import Compiler
>>> c = Compiler()
>>> c.collect(forms[0])
>>> c.sigs
{'fib': <FunctionSig fib -> i32(i32)>}
```

The signature of `fib` is now registered, **so the recursive call inside the body can find it**. That is the point of the two-pass scan.

### Step 4: the second pass (generating the body)

```python
>>> c.emit_top(forms[0])
>>> print(c.module.render())
```

```llvm
define i32 @l_fib(i32 %n) {
entry0:
  %t1 = icmp slt i32 %n, 2
  br i1 %t1, label %then1, label %else2
then1:
  br label %merge3
else2:
  %t2 = sub i32 %n, 1
  %t3 = call i32 @l_fib(i32 %t2)
  %t4 = sub i32 %n, 2
  %t5 = call i32 @l_fib(i32 %t4)
  %t6 = add i32 %t3, %t5
  br label %merge3
merge3:
  %t7 = phi i32 [ %n, %then1 ], [ %t6, %else2 ]
  ret i32 %t7
}
```

**That is all there is to it.** A 20-line Lisp function became 12 lines of IR.

### Step 5: line-by-line comparison

| Lisp | IR | Note |
|---|---|---|
| `(defn fib (n) ...)` | `define i32 @l_fib(i32 %n)` | name mangling (Chapter 17) |
| `(< n 2)` | `%t1 = icmp slt i32 %n, 2` | a comparison produces `i1` (Chapter 4) |
| `(if ...)` | `br i1 %t1, label %then1, label %else2` | conditional branch |
| `n` (then branch) | `br label %merge3` | `n` is a parameter, **no load needed** |
| `(- n 1)` | `%t2 = sub i32 %n, 1` | arithmetic |
| `(fib ...)` | `%t3 = call i32 @l_fib(i32 %t2)` | recursive call |
| `(+ (fib..) (fib..))` | `%t6 = add i32 %t3, %t5` | |
| merge | `%t7 = phi i32 [ %n, %then1 ], [ %t6, %else2 ]` | **the core of Chapter 18** |
| return | `ret i32 %t7` | |

### Step 6: verification

```bash
$ python3 compiler.py examples/fib.lisp > fib.ll
$ llvm-as-18 fib.ll -o fib.bc && echo VERIFIED
VERIFIED
```

### Step 7: link and run

```c
#include <stdio.h>
int l_fib(int);
int main(void) {
    for (int i = 0; i < 10; i++) printf("fib(%d)=%d\n", i, l_fib(i));
    return 0;
}
```

```bash
$ clang-18 -w main.c fib.bc -o fibtest && ./fibtest
fib(0)=0
fib(1)=1
fib(2)=1
fib(3)=2
fib(4)=3
fib(5)=5
fib(6)=8
fib(7)=13
fib(8)=21
fib(9)=34
```

**fib(9)=34. Correct.**

## 19.5 An honest statement: which code is "live"

This is the most important section of the chapter. Chapter 15 promised an honest statement of the boundaries.

### Fully used

| Module | Status |
|---|---|
| `lexer.py` | used in full |
| `reader.py` | used in full (except the `'` quote form, since the compiler does not understand `quote`) |
| `compiler.py`'s `Var`, `Frame`, `compile_expr`, `op_let`, `op_set`, `op_if`, `op_while`, `compile_call`, arithmetic/comparison, `to_i1` | used in full |
| `ir.py`'s `Block`, `Function`'s `new_block`/`start`/`emit`/`emit_value`/`branch`/`cond_branch`/`reserve_block`/`branch_placeholder`/`realize`/`alloca_slot`/`render`, and `Module` | used in full |

### Standby machinery (not currently called)

`ir.py` contains a **complete SSA construction mechanism** that is **not used**:

| Code | Why it is unused |
|---|---|
| `Function.var(name, ty)` | the compiler uses `read_var` directly and does not go through the SSA variable table |
| `Function.set_var(name, ty, v)` | as above |
| `Function._read_variable` | only called by `var` |
| `Function._add_phi_operand` | as above |
| `Function._complete_phi` | only called by `seal_block` |
| `Function.seal_block` | called in `op_while`, but since the variables all live in memory it has nothing to do |
| `Function.materialize_phis` | called by `render`, but no block contains a `phi` produced by this mechanism |
| The `Phi` class | as above |

**This is a real engineering phenomenon.** `ir.py` was designed as a **general** IR builder, capable of supporting a more advanced code generation strategy -- "promoting mutable variables to SSA values" (the sealed-block algorithm of Braun et al.). But the compiler in this book **chose the simpler route of "variables in memory"**, so that machinery sits idle.

### Why keep it

Three reasons:

1. **It demonstrates the complete SSA construction algorithm.** The root of that `phi` bug in Chapter 18 is "how to construct SSA when the predecessors are unknown" -- and this code is the systematic solution to exactly that problem. If you want to build a pure SSA front end, this is the starting point.
2. **`op_if` could have used it.** If the two branch values of an `if` were also brought into the variable table, `phi` would not have to be emitted by hand. Emitting by hand makes the mechanism **easier to see**, but the general machinery scales better.
3. **An honest architecture should permit unused abstractions.** A design in which every line of code is used often means the level of abstraction has been pushed too low.

**But the important thing is that this book tells you so explicitly.** Otherwise, reading the code, you would think `seal_block` is on the critical path and spend time understanding logic that never actually runs -- which is a waste of time.

> **This is also part of "avoiding a mismatch between description and reality"**: not only "the IR output in the book must match the real output", but also "the description of the code structure in the book must match the real code".

### A small experiment: proving that the machinery really is idle

Add a print statement inside `materialize_phis` in `ir.py`:

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

If you add `print("phi found", block.label)` before `if not phis: continue` and then compile `fib`, you will find that **nothing is printed at all** -- because the only `phi` in `l_fib` is text emitted by hand in `op_if`, and it is not in `bindings`.

**This verifies the claim.**

## 19.6 A few implementation notes

### Why `emit_top` and `collect` are written separately

Because they handle different **phases**:

```python
def collect(self, form):
    """First pass: register signatures only, generate no code."""
    if is_sym(head, "defn"):
        self._check_defn_shape(form)          # ← the shape check lives here
        name = form[1].name
        params = [p.name for p in form[2]]
        self.sigs[name] = FunctionSig(mangle(name), I32, [I32] * len(params))
```

**The shape check (`_check_defn_shape`) goes in the first pass**, because:

- if a `defn` is malformed, the error should be reported **before any IR is generated**;
- otherwise the user gets "half a module plus an exception", and it is hard to tell which part is trustworthy.

This is the "assert early" principle from section 16.6.

### Why `compile_expr` dispatches with `getattr`

```python
handler_name = OPERATOR_METHODS.get(head.name)
handler = getattr(self, handler_name, None) if handler_name else None
if handler is None:
    if head.name in self.sigs:
        return self.compile_call(fn, env, expr)
    raise IRError(f"unknown operator or function {head.name!r}")
return handler(fn, env, expr)
```

**Dispatch order**: special forms/operators -> user functions -> error.

This means: **a user cannot define a function called `if` that overrides the special form**. That is a deliberate design choice (unlike most Lisps; Scheme allows `if` to be shadowed). Simplicity wins here.

### Why `_binary` is so short

```python
def _binary(self, fn, env, expr, opname, ret_ty=I32):
    _, a, b = expr
    va = self.compile_expr(fn, env, a)
    vb = self.compile_expr(fn, env, b)
    return fn.emit_value(ret_ty, f"{opname} {va.ty} {va.name}, {vb.name}")

def op_add(self, fn, env, expr):
    return self._binary(fn, env, expr, "add")
```

Because **LLVM's instruction syntax is highly regular**: every binary operation is `<op> <type> <lhs>, <rhs>`. So ten operators (`add`/`sub`/`mul`/`sdiv`/`srem`/`icmp slt`/...) share a single helper.

**This is a sign that LLVM IR is well designed**: regular syntax keeps code generators short. Compare x86 assembly -- that back end needs hundreds of pattern-matching rules.

A comparison just passes an extra `ret_ty=I1`:

```python
def op_lt(self, fn, env, expr):
    return self._binary(fn, env, expr, "icmp slt", ret_ty=I1)
```

So `(< a b)` generates `icmp slt i32 %a, %b`, with type `i1`.

## 19.7 Exercises

**Exercise 19.1** Verify that `ir.py` is independent of the source language:

```bash
grep -n '"defn"\|"let"\|"set"\|"if"\|"while"\|Sym\|read_all' ir.py
```

There should be no output. Then think about why `grep -c "while"` gives a non-zero result. (Hint: Python has a `while` keyword.)

**Exercise 19.2** Add a print statement in `materialize_phis`, compile `fib`, `classify` and `sum_to`, and confirm that nothing is printed (proving that the SSA machinery is idle).

**Exercise 19.3** Add a `(do e1 e2 ...)` special form to the compiler (evaluate in order, return the last). How many lines does that take? (Hint: the body-handling logic of `op_let` can be reused directly.)

**Exercise 19.4** Add a `(- x)` form (unary negation) that generates `sub i32 0, %x` (Chapter 3). `op_sub` needs to be changed to check the argument count.

**Exercise 19.5** Give `compile_expr` a better error message for an "unknown symbol": if the symbol is neither a variable nor a function, suggest "did you forget to define it?" and list the defined function names.

**Exercise 19.6 (thought question)** If `op_if` were to use `ir.py`'s general SSA machinery (`set_var`/`var`/`seal_block`) instead of emitting `phi` by hand, what would have to change? What are the advantages and disadvantages?

## 19.8 Summary

- Four-layer architecture: `lexer` -> `reader` -> `compiler` -> `ir`, with one-way dependencies.
- **`ir.py` does not know that Lisp exists** and can be reused by any front end -- a small-scale instance of LLVM's idea that "front ends and back ends communicate through IR".
- The complete flow for `fib`: source -> tokens -> S-expressions -> signature -> IR -> verification -> linking -> execution, yielding `fib(9)=34`.
- **An honest statement**: the complete general SSA construction machinery in `ir.py` (`var`/`set_var`/`seal_block`/`Phi`) is **idle standby equipment**. The actual strategy is a **hybrid** (section 17.6): parameters use SSA values, `let` variables use stack slots, and the result of an `if` uses a **hand-emitted `phi`**.
- Operator dispatch uses an **explicit dictionary**, because `<`, `=` and `/` cannot serve directly as Python method names (the second real lesson after the numbered-value bug of Chapter 17).
- LLVM instruction syntax is regular, so ten binary operators share a single `_binary` helper.

The next chapter covers testing, verification and optimization.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 18 Control Flow and `phi` Nodes](18-ch18-control-flow-and-phi-nodes.md) · [Next: Chapter 20 Testing, Verification and Optimization →](20-ch20-testing-verification-and-optimization.md)
