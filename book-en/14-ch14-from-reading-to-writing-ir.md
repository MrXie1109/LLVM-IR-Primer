# Chapter 14 From Reading IR to Writing IR: Build Order and Lifetime

## 14.1 Referring Back: How That IR from Chapter 2 "Grew"

Go back to Chapter 2 for a moment. There you saw:

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
  store i32 %0, ptr %4, align 4
  ...
  %9 = mul nsw i32 %7, %8
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
  ret i32 %11
}
```

The explanation at the time was "`alloca` serves the debugger". That was the **why**. What this chapter answers is the **how**: in what order must a program do things to produce the text above?

The key to the answer is this: **this text has an order, and that order is not arbitrary.**

The line `%9 = mul nsw i32 %7, %8` must appear **after** `%7` and `%8` are defined. `ret i32 %11` must appear after `%11` is defined. And the three `alloca`s crowding at the top with `store` immediately following — that order is the **deliberate** arrangement of a generator, not a coincidence.

So the core question of writing an IR generator is:

> **"Where should I write the new instruction right now?"**

This "current position" has a formal name: the **insertion point**.

This chapter has a second callback as well. In Chapter 5 we said:

> **Under `-O0` variables live in memory, so `phi` is rare.**

This chapter explains that design decision **from the generator's point of view** — it is not laziness, but an exchange of the hard problem of dominance analysis for a few extra memory accesses. In Chapter 17 you will see how this trade-off makes our compiler simple and reliable.

## 14.2 The Insertion Point: A Cursor

Imagine you are editing a text file. You do not have an "append to the end" style of writing; instead you have a **cursor**, new text is inserted at the cursor, and the cursor advances after the insertion.

The insertion point of an IR generator is slightly more complicated, because it has a two-level structure:

```
function
├── basic block A   ← the insertion point can point at "the end of A"
│   ├── instruction 1
│   └── instruction 2
├── basic block B
│   └── instruction 3
└── basic block C
```

The insertion point is determined jointly by **which basic block** and **which position inside the block**. The overwhelming majority of the time the position is "the end of the block" (because we generate instructions in sequence), so in practice the insertion point is often simplified to "the current basic block".

**This is why a generator usually has a `current` field.**

```python
class Function:
    def __init__(self, ...):
        self.current = None      # ← insertion point

    def start(self, block):
        """Move the insertion point to the end of block."""
        self.current = block
        return block

    def emit(self, text):
        """Insert one instruction at the current insertion point."""
        self.current.add(text)
```

`emit` is only one line, but it is the hub of the whole generator: **every instruction that comes into being ultimately passes through it, and therefore every instruction automatically lands in the right block.**

## 14.3 First Principle: Create the Basic Block First, Then Fill It with Instructions

Here is the pitfall that beginners fall into most easily, and the error message it produces is very hard to understand.

### The Wrong Way

```python
# I want to generate a function whose first instruction is ret
fn = Function("f", I32, [I32, I32])
fn.emit("ret i32 0")          # ← the insertion point is not set yet!
```

If you `emit` while `current` is `None`, you get an `AttributeError` — that error is still reasonably friendly. But if your implementation "creates the block automatically", you get something worse:

```llvm
define i32 @f(i32, i32) {
  ret i32 0
}
```

This **looks** fine, and `llvm-as-18` will even accept it! But it is semantically wrong: a block with no label is an "anonymous entry block", and when you later want to add something to it you will find that you can no longer get hold of that block.

### The Right Way

```python
fn = Function("f", I32, [I32, I32])
entry = fn.new_block("entry")   # 1. create the block first
fn.start(entry)                 # 2. move the insertion point into it
fn.emit("ret i32 0")            # 3. only now fill in instructions
```

**The order cannot be reversed.** Remember this three-step pattern:

> **new_block → start → emit**

Mix the creation and the filling of a `merge_block` together and you will hit this ordering problem. The error that the LLVM verifier gives is very convoluted:

```
PHI node entries do not match predecessors!
  %t5 = phi i32 [ %t2, %then1 ], [ %t4, %else2 ]
label %else2
label %merge6
```

What this error means is: "your `phi` claims that `%else2` branches to me, but `%else2` actually branches to `%merge6`." — The root cause is that the insertion point drifted. Chapter 18 revisits this bug in full.

### Why the Basic Block Must Be Created First

Because of **forward references**. Look at this IR:

```llvm
entry:
  %c = icmp slt i32 %x, 0
  br i1 %c, label %then, label %else
then:
  br label %merge        ; ← refers to %merge
else:
  br label %merge        ; ← refers to %merge
merge:                   ; ← %merge is only "defined" here
  ret i32 0
```

The `br` in the `then` block references `%merge`, but the **contents** of `%merge` are not written until later. Textually, this is a forward reference.

How would a purely textual generator handle it? It might first write `br label %merge` as a string, and substitute in the contents once `%merge` has some. But that is very fragile.

The better approach is to **separate "name" from "contents"**. Create the block object first (the name is settled) and leave the contents empty; fill in the contents when the time actually comes. This is why our `Block` has an `instructions` list rather than holding text directly.

```python
def new_block(self, label):
    block = Block(label)          # the name exists right now
    self.blocks.append(block)
    return block
    # note: block.instructions is empty at this moment
```

**Creating ≠ filling.** This is the most important sentence in this chapter.

## 14.4 Second Principle: Definitions Must Dominate Uses

SSA form has one iron rule:

> **The definition of a value must dominate all of its uses.**

"Dominate" means: **starting from the function entry, every path that reaches any use point must necessarily pass through the definition point.**

Here is a counterexample. This IR is **illegal**:

```llvm
define i32 @f(i32 %a, i1 %cond) {
entry:
  br i1 %cond, label %t, label %f
t:
  %x = add i32 %a, 1        ; %x is defined only in t
  br label %m
f:
  br label %m
m:
  %y = add i32 %x, 1        ; ← illegal! coming from f to m, %x is not defined at all
  ret i32 %y
}
```

`llvm-as-18` rejects it:

```bash
$ llvm-as-18 bad_dom.ll -o /dev/null
llvm-as-18: assembly parsed, but does not verify as correct!
Instruction does not dominate all uses!
  %x = add i32 %a, 1
  %y = add i32 %x, 1
```

**This rule places enormous demands on the design of a generator.** It means that when you generate `%y = add i32 %x, 1`, you must **already** have guaranteed that "no matter which path is taken, `%x` is determined".

This is why the compiler in this book ultimately chose the strategy of "put mutable variables in `alloca`" (Chapter 17). Once a variable lives in memory, the value produced by `load` is a **freshly defined value in the current block**, which trivially dominates its own use point — you do not need to do any dominance analysis at all.

**Trade memory for simplicity of SSA construction** — this is what clang `-O0` does, and it is what we do. When `mem2reg` later promotes these memory operations to SSA, it does the dominance analysis and inserts the `phi` nodes **for us** (both Chapter 5 and Chapter 20 measure this).

> In Chapter 2 you were puzzled to see that `-O0` IR is bloated; in Chapter 14 you see the **engineering reason** for that bloat: it lowers the generator's complexity from "needs a complete dominator tree" to "emit instructions in order". This is not clang being lazy; it is a deliberate trade-off.

## 14.5 Third Principle: Every Basic Block Must End with a Terminator

A basic block is by definition "a sequence of instructions with exactly one entry and one exit". The terminator (`ret`, `br`, `switch`, `unreachable`) is that exit.

**No instruction may follow a terminator.** LLVM reports an error already during text parsing:

```llvm
define i32 @f() {
entry:
  ret i32 0
  %x = add i32 1, 2      ; ← parse error
}
```

```bash
$ llvm-as-18 bad_after_term.ll -o /dev/null
llvm-as-18: bad_after_term.ll:5:1: error: expected instruction opcode
}
^
```

The error message `expected instruction opcode` means "a new basic block should start here" — because the parser considers `ret` to have ended the current block, so what follows must be a label or a new `define`.

**What if a block has no terminator?** The result is **exactly the same**:

```llvm
define i32 @f(i32 %a) {
entry:
  %x = add i32 %a, 1
}
```

```bash
$ llvm-as-18 no_term.ll -o /dev/null
llvm-as-18: no_term.ll:4:1: error: expected instruction opcode
}
^
```

**Two different mistakes, one identical error message.** At first sight this is confusing, but it is actually reasonable: when the parser reads `}`, both cases present themselves as "I am still expecting the next instruction, but I have hit the end of the function".

> **This is exactly the lesson**: LLVM's errors point at the **text**, whereas what you need to diagnose is the **generation logic**. When you see `expected instruction opcode`, you should suspect both "a stray instruction" and "a missing terminator" — and the generator's own assertions (Section 14.7) can tell the two apart.

**So in a generator, both of these constraints should be asserted up front.**

## 14.6 The Minimal Skeleton: Generating an `add` Function

Now let us turn the principles above into a program that actually runs. It does one thing only: it generates

```llvm
define i32 @add(i32 %a, i32 %b) {
entry:
  %t1 = add i32 %a, %b
  ret i32 %t1
}
```

Here is the code. It is only about 100 lines, and it **hardly goes beyond the rules explained in the preceding sections**.

```python
#!/usr/bin/env python3
"""minimal_codegen.py -- generate an add function, and nothing more.

This file is the product of Chapter 14, and the prototype of the project
skeleton in Chapter 15. Its only reason to exist is to turn the two concepts
of "insertion point" and "separation of creation from filling" into something
that can be run and verified.
"""


class Block:
    """A basic block: it has a name, a list of instructions, and possibly a terminator."""

    def __init__(self, label):
        self.label = label
        self.instructions = []
        self.terminator = None

    def add(self, text):
        """Append one instruction to the end of the current block."""
        if self.terminator is not None:
            # Nothing may follow the terminator: that is the definition of a basic block.
            raise RuntimeError(
                f"block %{self.label} already terminated; cannot add: {text}"
            )
        self.instructions.append("  " + text)

    def terminate(self, text):
        """Set the terminator. A block can have only one."""
        if self.terminator is not None:
            raise RuntimeError(f"block %{self.label} already has a terminator")
        self.terminator = "  " + text

    def render(self):
        if self.terminator is None:
            raise RuntimeError(f"block %{self.label} has no terminator")
        lines = [f"{self.label}:"] + self.instructions + [self.terminator]
        return "\n".join(lines)


class Function:
    """A function: several basic blocks, plus one "insertion point"."""

    def __init__(self, name, ret_ty, param_types, param_names):
        self.name = name
        self.ret_ty = ret_ty
        self.param_types = param_types
        self.param_names = param_names
        self.blocks = []
        self.current = None          # insertion point
        self.temp = 0

    def new_block(self, label):
        """Create only; do not fill."""
        block = Block(label)
        self.blocks.append(block)
        return block

    def start(self, block):
        """Move the insertion point to the end of this block."""
        self.current = block
        return block

    def new_temp(self):
        self.temp += 1
        return f"%t{self.temp}"

    def emit(self, text):
        """Insert one instruction at the current insertion point."""
        if self.current is None:
            raise RuntimeError(
                "insertion point is not set; call start(new_block(...)) first"
            )
        self.current.add(text)

    def emit_value(self, ty, text):
        """Insert an instruction that produces a value, and return its name."""
        name = self.new_temp()
        self.emit(f"{name} = {text}")
        return name

    def terminate(self, text):
        """Set the terminator at the end of the current block."""
        if self.current is None:
            raise RuntimeError(
                "insertion point is not set; call start(new_block(...)) first"
            )
        self.current.terminate(text)

    def render(self):
        params = ", ".join(
            f"{ty} {n}" for ty, n in zip(self.param_types, self.param_names)
        )
        out = [f"define {self.ret_ty} @{self.name}({params}) {{"]
        for block in self.blocks:
            out.append(block.render())
        out.append("}")
        return "\n".join(out)


def generate_add():
    """Generate define i32 @add(i32 %a, i32 %b)."""
    fn = Function("add", "i32", ["i32", "i32"], ["%a", "%b"])

    # ---- the three-step pattern: new_block -> start -> emit ----
    entry = fn.new_block("entry")
    fn.start(entry)

    r = fn.emit_value("i32", "add i32 %a, %b")
    fn.terminate(f"ret i32 {r}")

    return fn.render()


if __name__ == "__main__":
    print(generate_add())
```

Run it:

```bash
$ python3 minimal_codegen.py
define i32 @add(i32 %a, i32 %b) {
entry:
  %t1 = add i32 %a, %b
  ret i32 %t1
}
```

**Notice that this uses the named value `%t1`, not a numbered value.** Chapter 8 explained why: named values completely bypass LLVM's rules about "parameters + anonymous blocks + instructions with results sharing one counter". Chapter 17 shows what happens when you overreach and try to imitate the numbering rules.

### Verify It

**Never trust the IR you generate.** Verify it with `llvm-as-18`:

```bash
$ python3 minimal_codegen.py > add.ll
$ llvm-as-18 add.ll -o add.bc && echo "VERIFIED"
VERIFIED
```

Now change the function name to `main` and execute it directly:

```bash
$ python3 - <<'EOF' > addmain.ll
import sys; sys.path.insert(0, '.')
from minimal_codegen import Function
fn = Function("main", "i32", [], [])
e = fn.new_block("entry"); fn.start(e)
r = fn.emit_value("i32", "add i32 40, 2")
fn.terminate(f"ret i32 {r}")
print(fn.render())
EOF

$ llvm-as-18 addmain.ll -o addmain.bc
$ lli-18 addmain.bc; echo "exit=$?"
exit=42
```

`exit=42` — you have just **generated and executed** a piece of LLVM IR with about 100 lines of Python. This is the starting point of Part III.

## 14.7 The Skeleton's Self-Defence

Look back at that skeleton: three assertions were added on purpose. They will save you many times later.

**Assertion one: no instruction may be added after the terminator.**

```python
def add(self, text):
    if self.terminator is not None:
        raise RuntimeError(
            f"block %{self.label} already terminated; cannot add: {text}"
        )
```

This assertion catches the error "an instruction was emitted after the terminator" **on the very line where it happens**.

**Assertion two: `emit` fails when the insertion point is not set.**

Measured:

```bash
$ python3 -c "
import sys; sys.path.insert(0, '.')
from minimal_codegen import Function
fn = Function('f','i32',[],[])
fn.emit('ret i32 0')
"
RuntimeError: insertion point is not set; call start(new_block(...)) first
```

This one catches the "forgot to call `start`" error on the very line where it happens, instead of waiting until the file has been generated and `llvm-as` reports an error pointing somewhere else.

**Assertion three: a block must have a terminator.**

```python
def render(self):
    if self.terminator is None:
        raise RuntimeError(f"block %{self.label} has no terminator")
```

This one checks at **output** time, because "is the block terminated" can only be judged once the block has been fully written.

> **The generality of this pattern**: a generator should maintain its invariants at its own level of abstraction and report an error immediately when they are violated. If you let illegal state flow into the output text, you have outsourced the debugging work to the LLVM parser — and its error messages are about the **text**, not about **your generation logic**. In Chapter 16 we design AST validation with the same idea.

## 14.8 From Skeleton to Complete Compiler: What Is Still Missing

This skeleton can already generate straight-line code. To become the complete compiler of Part III, four more pieces are needed:

| Gap | Filled in which chapter |
|---|---|
| Lexing and parsing (turning Lisp text into an AST) | Chapter 16 |
| Expressions, variables, function calls | Chapter 17 |
| Control flow: `br`, `phi`, loops | Chapter 18 |
| Testing, verification and working with `mem2reg` | Chapter 20 |

**Control flow is the hardest piece**, because it pulls on both of the principles explained in this chapter at once:

- Branching means you have to generate **multiple paths**, and each path has to maintain its insertion point independently;
- Merging means you need `phi`, and the operands of `phi` are **basic blocks**, so you must guarantee that those blocks are **already created** (even if not yet filled).

And there is a more insidious pitfall: **nested control flow can silently swap out the "current block" while a subexpression is being compiled**. Chapter 18 analyses this pitfall in detail, along with the error messages it produces.

## 14.9 Summary

- The core concept of generating IR is the **insertion point**: where new instructions are inserted.
- The order of generation is not free: **a definition must precede its use** (textual order), and **a definition must dominate its uses** (SSA semantics).
- Basic blocks are **created first and filled later**. Creation brings the name, filling brings the contents, and only by separating the two can forward references be supported.
- The three-step pattern: **`new_block` → `start` → `emit`**.
- Every basic block **must end with a terminator**, and no instruction may follow the terminator.
- "Put mutable variables in `alloca`" is not laziness but **trading memory for the elimination of dominance analysis** — this is exactly clang's `-O0` strategy, and it is our compiler's strategy too.
- A generator should assert its invariants at its own level ("insertion point is set", "block is not terminated", "block is terminated"), rather than handing illegal text to LLVM to discover.
- **Use named values rather than numbered values when generating temporaries**, which completely bypasses the counter rules of Chapter 8.

In the next chapter we start work in earnest: designing the Lisp dialect and setting up the project skeleton.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 13 The Optimization Pipeline and `opt`](13-ch13-the-optimization-pipeline-and-opt.md) · [Next: Chapter 15 Language Design and Project Skeleton →](15-ch15-language-design-and-skeleton.md)
