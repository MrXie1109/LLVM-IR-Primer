# Chapter 1 Why LLVM IR Is Worth Learning

## 1.1 A real dilemma

Suppose you have written this piece of C:

```c
int mul_add(int x, int y, int z) {
    return x * y + z;
}
```

It is correct, and the compiler knows it is correct. But when you want to know "is it actually fast," "why is it slow here," or "what does `-O2` actually do," the level of C is no longer enough. Assembly can give you the answer, but assembly is the **endgame**: it mixes register allocation, instruction selection, and stack frame layout all together, and it is hard to tell from it "which decision is at the language level and which is at the machine level."

LLVM IR sits exactly in between. It is closer to the machine than C:

- It is **three-address code**, with no nested expressions;
- It has **types**, but not the far more complicated implicit conversions of C;
- Its control flow is represented as an **explicit jump graph**.

And it is closer to the language than assembly:

- It has **infinitely many virtual registers**, so you need not worry about register allocation;
- Its types and operations are **target-independent**;
- It is **readable, writable, and verifiable**.

## 1.2 Five reasons you should learn it

**Reason one: it is the lingua franca of modern compilers.**

Clang, Rust, Swift, Julia, Zig, TensorFlow XLA, TVM — their back ends are either LLVM directly or modelled on LLVM's design. Once you know IR, you can read the output of these compilers without having to learn each of their internal structures one by one.

**Reason two: it makes you truly understand "undefined behaviour."**

C's undefined behaviour (UB) is an abstract stipulation at the language level. At the IR level, you see it turn into something very concrete: an `nsw` flag, an `inbounds` marker, a `poison` value. You will see with your own eyes why the "obviously true" judgement `x + 1 > x` does not hold when there is signed overflow, and how the compiler exploits that.

**Reason three: it is a scalpel for performance analysis.**

When `-O2` does not meet your expectations, you need to know which optimization step failed to take effect. `opt -passes=...` lets you break the optimization pipeline into single steps and watch how the IR changes, step by step. Looking at assembly cannot give you this ability, and neither can looking at source code.

**Reason four: writing a front end is more realistic than you think.**

For a usable language front end, the hard part is not parsing but **generating correct IR**. Especially the SSA form — which value should a variable take at a control-flow merge point? This is a real problem, and Part 3 of this book takes you through solving it from scratch.

**Reason five: it is a craft you can teach yourself.**

IR has few syntactic constructs, and almost every one of them can be verified immediately with `clang` or `llvm-as`. That means you can explore on your own, without depending on the authority of some textbook.

## 1.3 The methodology of this book: side-by-side comparison

Part 1 of this book teaches with only one method:

> **A piece of C on the left, a piece of IR on the right, compared line by line, explaining why each line exists.**

Take an example. This is the C:

```c
int add(int a, int b) { return a + b; }
```

This is the IR that `clang-18 -S -emit-llvm -O0` gives it on LLVM 18.1.3 (irrelevant module-level information omitted):

```llvm
define dso_local i32 @add(i32 noundef %0, i32 noundef %1) #0 {
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  store i32 %0, ptr %3, align 4
  store i32 %1, ptr %4, align 4
  %5 = load i32, ptr %3, align 4
  %6 = load i32, ptr %4, align 4
  %7 = add nsw i32 %5, %6
  ret i32 %7
}
```

Now you may be thinking: "What about that 'three-address code' you promised? Why does one `add` need 8 instructions and two memory allocations?"

**That is a very good question**, and it is exactly the entire content of Chapter 2 of this book. Here is a short answer first, so you know where we are heading:

- Under `-O0`, clang **stores every function parameter to the stack**, because that is the only way the debugger (gdb) can see the variable's value at any moment;
- The actual computation is really only the single instruction `add nsw i32 %5, %6`;
- Add `-O2`, and clang compresses the whole thing to `add nsw i32 %1, %0`; only then does the phrase "three-address code" hold.

This brings us to the first principle of this book:

## 1.4 The first principle of this book: don't trust memory, trust the terminal

There are many textbooks and blog posts about LLVM IR, and quite a few of them are outdated in some detail. The most common categories of error:

1. **Pointer types**: older material writes `i32*`, `%struct.Point*`. LLVM 18 uses **opaque pointers**, always written `ptr`. LLVM 18 still accepts the old spelling, but **silently** rewrites it to `ptr` for you — we will demonstrate this in practice in Chapter 9.
2. **The `opt` command line**: older material writes `opt -mem2reg`. LLVM 18 errors out immediately:

   ```
   $ opt-18 -mem2reg -S input.ll
   The `opt -passname` syntax for the new pass manager is not supported,
   please use `opt -passes=<pipeline>` (or the `-p` alias ...)
   ```

3. **The operands of `getelementptr`**: the old spelling repeats the pointer type twice; the new spelling mentions the type only once.

The approach of this book is: **every assertion about "what the output looks like" comes with the actual run result**. You can, and should, check it on your own machine.

## 1.5 Environment setup

You need LLVM 18 and Python 3. On Ubuntu:

```bash
sudo apt install clang-18 llvm-18 llvm-18-tools
```

Verify:

```bash
$ clang-18 --version
Ubuntu clang version 18.1.3 (1ubuntu1)

$ llvm-as-18 --version
Ubuntu LLVM version 18.1.3
```

This book uses the following tools; here is a first introduction to them:

| Tool | Purpose | Analogy |
|---|---|---|
| `clang-18 -S -emit-llvm` | C → IR text | "Translating" C into IR |
| `llvm-as-18` | IR text → binary `.bc`, **and verifies** | The assembler + syntax checker for IR |
| `llvm-dis-18` | Binary `.bc` → IR text | Disassembler |
| `opt-18` | Run optimization passes on IR | The "compiler" for IR |
| `llc-18` | IR → target assembly | The back end for IR |
| `lli-18` | Directly interpret and execute IR | The interpreter for IR |

A minimal complete workflow — try it right now:

```bash
$ cat > hello.ll <<'EOF'
define i32 @main() {
  ret i32 42
}
EOF

$ llvm-as-18 hello.ll -o hello.bc
$ lli-18 hello.bc; echo "exit=$?"
exit=42
```

`lli` executed this piece of IR, `main` returned 42, so the process exit code is 42. (Note: the return value of `main` is truncated to 8 bits by the shell, so if you return 256, you will see `exit=0`. This is not a problem with LLVM; it is a Unix convention.)

## 1.6 The three parts of this book

**Part 1 (Chapters 1–7)** is "reading." You will see a great many side-by-side comparisons of C and IR, with the goal of building intuition: on seeing a C construct, the shape of the IR should come to mind.

**Part 2 (Chapters 8–14)** is "writing." Building on the intuition established in Part 1, it systematically fills in the syntax. You will begin to write `.ll` files by hand and check them back and forth with `llvm-as-18`.

**Part 3 (Chapters 15–20)** is "building." You will write a real compiler in Python, compiling Lisp into LLVM IR, and use the LLVM verifier and the C linker to prove that it is correct.

## 1.7 Summary

- LLVM IR is the common language between compiler front ends and back ends; it is closer to the machine than C and closer to the language than assembly.
- The biggest obstacle to learning it is not the syntax but **outdated material**.
- The principle of this book: everything is governed by the actual output of LLVM 18.1.3.
- You already know how to write, verify, and execute IR — right there in those five lines of Section 1.5.

In the next chapter, we take apart the first function for real.

---

<!-- nav -->
[Contents](00-preface.md) · [Next: Chapter 2 Your First IR: The Three-Line Truth About `mul_add` →](02-ch02-your-first-ir-mul-add.md)
