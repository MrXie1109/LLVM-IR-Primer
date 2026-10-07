# LLVM IR Primer: A Complete Guide from C to Lisp

**Based on LLVM 18.1.3**

---

## An important statement about versions

**Every piece of IR output** in this book was actually produced or verified by the following toolchain:

```
$ clang-18 --version
Ubuntu clang version 18.1.3 (1ubuntu1)
Target: x86_64-pc-linux-gnu
Thread model: posix
InstalledDir: /usr/bin

$ llvm-config-18 --version
18.1.3

$ llc-18 --version
Ubuntu LLVM version 18.1.3
  Optimized build.
  Default target: x86_64-pc-linux-gnu

$ python3 --version
Python 3.12.3
```

**Why insist on the version?** LLVM IR is not a frozen specification; it evolves with every major release. The same C function may produce significantly different IR on LLVM 15, 18, and 19. Here are a few examples that recur throughout the book:

| Change point          | Older versions (≤14)                                   | LLVM 18.1.3                                              |
| --------------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| Pointer types         | `i32*`, `%struct.Point*`                               | Unified as `ptr`                                         |
| Struct field access   | `getelementptr %struct.P, %struct.P* %p, i32 0, i32 1` | `getelementptr inbounds %struct.P, ptr %p, i32 0, i32 1` |
| `opt` usage           | `opt -mem2reg`                                         | `opt -passes=mem2reg` (the old syntax **errors out**)    |
| Typed pointers        | The standard spelling                                  | Still accepted, but **silently rewritten** to `ptr`      |

This book uses the LLVM 18.1.3 spelling throughout. If you are on a different version, trust the output on your own machine — which is exactly why this book keeps teaching you to "verify with tools, not from memory."

---

## Who this book is for

You do not need a compiler background. You need:

- The ability to write C, and to read pointers and structs;
- A little Python, enough to read classes and dictionaries;
- A computer with LLVM 18 installed, and a bit of curiosity.

Compiler courses often intimidate people, because they "descend" from lexing to parsing to semantic analysis, and you do not see real machine code until page 300. This book **goes the other way**:

> **First you see what the IR for a piece of C code looks like, then you look back and understand "why it was designed this way," and finally you write a compiler that generates such IR yourself.**

The advantage of this order is that you always have a concrete, runnable reference point. Every time you learn a new concept, you can verify it immediately with `clang`.

---

## Structure of the book

The book has 20 chapters in three parts. Click any chapter to jump straight to it.

### Part 1: LLVM IR through a C programmer's eyes (Chapters 1–7)

Starting from the C functions you know best, it takes apart the output of `clang -S -emit-llvm` line by line. The core methodology is **side-by-side comparison**: every piece of C code is paired with a piece of IR, explained line by line.

| Chapter | Title | Core content |
|---|---|---|
| [Chapter 1](01-ch01-why-learn-llvm-ir.md) | Why LLVM IR Is Worth Learning | Side-by-side comparison, environment setup, five reasons |
| [Chapter 2](02-ch02-your-first-ir-mul-add.md) | Your First IR: The Three-Line Truth About `mul_add` | `-O0` is 12 instructions, not 3; why `alloca` exists |
| [Chapter 3](03-ch03-arithmetic-logic-and-shifts.md) | Arithmetic, Logic and Shifts | `nsw`, `sdiv`/`udiv`, `ashr`/`lshr` |
| [Chapter 4](04-ch04-comparisons-and-i1.md) | Comparisons and the Tyranny of `i1` | `icmp` predicates, `fcmp`, `&&`/`\|\|` need branches |
| [Chapter 5](05-ch05-control-flow-and-phi.md) | Control Flow: `br`, Basic Blocks and `phi` | What `phi` is, `select` and `switch`, the `mem2reg` experiment |
| [Chapter 6](06-ch06-memory-and-getelementptr.md) | Memory, Pointers and `getelementptr` | GEP only computes addresses, double indexing, `inbounds` |
| [Chapter 7](07-ch07-functions-and-calls.md) | Functions, Calling Conventions and Linkage | `define`/`declare`, indirect calls, `unreachable` |

### Part 2: The full landscape of LLVM IR syntax (Chapters 8–14)

Building on the intuition from Part 1, it systematically covers every syntactic construct of IR. The design principle is **letting "why" drive "what"**: rather than presenting syntax in isolation, it explains "which features of C forced LLVM to design this syntax."

**Every chapter starts from a concrete example in Part 1**, so the "what" of Part 2 always hangs off the "you have seen it" of Part 1.

| Chapter | Title | Referring back to Part 1 |
|---|---|---|
| [Chapter 8](08-ch08-identifiers-and-naming.md) | Modules, Identifiers and Naming Rules | Where did `%3` from Chapter 2 go |
| [Chapter 9](09-ch09-the-type-system.md) | The Type System | `%struct.Point` from Chapter 6 |
| [Chapter 10](10-ch10-constants-and-globals.md) | Constants, Global Variables and Linkage | `@g_counter` from Chapter 6, `null` from Chapter 4 |
| [Chapter 11](11-ch11-instruction-reference.md) | The Instruction Reference | `zext i1 %3 to i32` from Chapter 4 |
| [Chapter 12](12-ch12-attributes-metadata-and-intrinsics.md) | Attributes, Metadata and Intrinsics | That omitted `attributes` line from Chapter 2 |
| [Chapter 13](13-ch13-the-optimization-pipeline-and-opt.md) | The Optimization Pipeline and `opt` | That "nothing happened" experiment from Chapter 2 |
| [Chapter 14](14-ch14-from-reading-to-writing-ir.md) | From Reading IR to Writing IR: Build Order and Lifetime | How that IR from Chapter 2 "grew" |

### Part 3: A hand-written Lisp → LLVM IR compiler (Chapters 15–20)

You implement a **real** compiler in Python. Lisp is chosen as the source language because its S-expression syntax is extremely concise, letting you put all your energy into "how to generate IR" instead of parsing the source language.

| Chapter | Title | Core content |
|---|---|---|
| [Chapter 15](15-ch15-language-design-and-skeleton.md) | Language Design and Project Skeleton | **No closures/dynamic typing/GC/tail-call optimization**; the layering of four files |
| [Chapter 16](16-ch16-lexing-and-parsing.md) | Lexing and Parsing | The ambiguity of `-`, `Sym` interning, a 40-line parser |
| [Chapter 17](17-ch17-code-generation.md) | Code Generation: Expressions, Variables and Calls | The trade-offs of `alloca`, name mangling, **the numbered-value trap** |
| [Chapter 18](18-ch18-control-flow-and-phi-nodes.md) | Control Flow and `phi` Nodes | Generating `phi` by hand, **the step most likely to go wrong** |
| [Chapter 19](19-ch19-a-complete-walkthrough.md) | A Complete Code Walkthrough | `fib` end to end, **honestly stating which code is unused** |
| [Chapter 20](20-ch20-testing-verification-and-optimization.md) | Testing, Verification and Optimization | 22/22 tests, empirical `mem2reg`, comparison with clang's `-O2` |

### Appendices

The main text follows the main line, and three kinds of content that are "unrelated to the current chapter's main line but genuinely useful" have been moved to the appendices, so as not to interrupt the reading rhythm.

| Appendix | Content | When to read it |
|---|---|---|
| [Appendix A](21-appendix-a-differences-from-common-claims.md) | Differences from Common Claims | When writing `.ll` after other material gives you errors; when your output does not match |
| [Appendix B](22-appendix-b-optimization-primer.md) | Optimization Primer: From `-O0` to `-O2` | When you want to know "how `alloca` disappears" or "what `-O2` does" |
| [Appendix C](23-appendix-c-compiler-implementation-notes.md) | Compiler Implementation Notes | When reading Part 3 and wanting to go deeper on a design trade-off |
| [Appendix D](24-appendix-d-instruction-quick-reference.md) | **LLVM IR Instruction Quick Reference** | **For looking things up anytime**: which instruction a C operation maps to, syntax, flags, predicates |

**If you take only one piece of material with you to the machine, take Appendix D.** It is organized four ways — "look up by task," "look up by syntax," "look up by flag," and "the complete table of comparison predicates" — covering the vast majority of lookup needs when writing IR.

### Suggested reading paths

- **Complete newcomer to LLVM**: read straight through in order to Chapter 20.
- **Only want to know "what IR did my C code become"**: read Part 1 (Chapters 1–7), then Chapter 13 (the optimization pipeline).
- **Want to write your own compiler front end**: Chapters 5 and 6 of Part 1 + Chapters 8, 9, and 11 of Part 2 + all of Part 3.
- **Want to understand `phi`**: Chapter 5 → Chapter 14 → Chapter 18; this path is devoted to SSA and control flow.

---

## The Part 3 compiler is real and runnable

The compiler in Part 3 is not pseudocode. It consists of the following files, all of which pass their tests on LLVM 18.1.3:

```
code/
├── README.md       source index: which chapter each file belongs to
├── part1-c/        Part I C sources (37 .c files)
├── part2-ir/       Part II hand-written .ll (14, 3 deliberately invalid)
├── part3-lispc/    the Part III compiler
│   ├── lexer.py        lexer
│   ├── reader.py       parser (S-expressions)
│   ├── ir.py           LLVM IR builder
│   ├── compiler.py     code generator
│   ├── tests.py        end-to-end tests (22 cases)
│   ├── minimal_codegen.py   the minimal skeleton from Chapter 14
│   └── examples/       Lisp example programs
└── extra/          C driver files used by the book's examples
```

The test suite does four things for each case:

1. Compile the Lisp source into LLVM IR text;
2. Assemble it with `llvm-as-18` — **this step runs the LLVM verifier**, the iron-fisted judge of whether the IR we generate is legal;
3. Have `clang-18` link the generated object file with a C driver;
4. Run the program and compare the output.

```
$ python3 tests.py
PASS  mul_add
PASS  nested_arith
...
22/22 passed
```

---

## How to read this book

**You must get hands-on.** Whenever you see a piece of IR, run it on your own machine:

```bash
clang-18 -S -emit-llvm -O0 yourfile.c -o -
```

**When something disagrees, trust your terminal.** The book deliberately keeps several examples where "the common textbook claim is actually wrong" — for instance, `mul_add` is not three lines of IR under `-O0`. In these places the book does not gloss over it, but explains the real output and the reason behind it together.

**Do not memorize syntax.** IR has few syntactic constructs, and every one of them has a clear engineering justification. Once you understand the justification, the syntax sticks by itself.

---

## Conventions

- IR output in the book omits lines irrelevant to teaching, such as `; ModuleID`, `source_filename`, and `!llvm.ident`, as well as the verbose `attributes #0 = {...}`; wherever something is omitted, the text says so.
- Commands always use version-suffixed tool names (`clang-18`, `opt-18`, `llvm-as-18`), to avoid confusion with other LLVM versions on your system.
- **All accompanying source code is collected in the `code/` directory of this repository**, divided by position in the book into `part1-c/` (C sources), `part2-ir/` (hand-written `.ll`), `part3-lispc/` (the Part 3 compiler), and `extra/` (C driver files). `code/README.md` is the index, listing which chapter each file corresponds to.

## How this book was verified

A core promise of this book is that **"the description matches reality."** To that end:

- **Every piece of IR output** appearing in Parts 1 and 2 was actually produced by running `clang-18` / `llvm-as-18` / `opt-18` / `llc-18` on LLVM 18.1.3.
- The Part 3 compiler is **real and runnable**, and all 22 end-to-end tests pass; every piece of generated IR in the book was copied from an actual run.
- The **error messages** mentioned in the book are all verbatim captures from real runs, including the verifier's messages about mismatched `phi` predecessors, backwards numbering, and unequal types.
- Wherever a "common textbook claim" disagrees with measurement, it is collected in [Appendix A](21-appendix-a-differences-from-common-claims.md) with the real output, rather than being glossed over or allowed to disturb the reading rhythm of the main text.

Every piece of IR, every error message, and every number in the book has been checked one by one against the output of the real toolchain.

If your output disagrees with the book, **trust your terminal**, and check your LLVM version — which is exactly why this book keeps emphasizing "verify with tools, not from memory."

Now, let us start from the smallest function.
