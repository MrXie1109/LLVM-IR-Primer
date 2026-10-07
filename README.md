# LLVM IR Primer — From C to Lisp

**A hands-on guide to LLVM IR, verified against LLVM 18.1.3**

[中文版](book-zh/00-前言.md) · [English](book-en/00-preface.md)

---

## What this is

Most LLVM material starts at the compiler front end and works *down* toward IR. This book goes the
other way: you first see what the IR for a familiar C function looks like, then work backwards to
understand *why* it is designed that way, and finally build a compiler that emits it yourself.

No compiler background is required. You need C, a little Python, and LLVM 18.

## Structure

**Part I — LLVM IR Through a C Programmer's Eyes (ch. 1–7).**
Take `clang -S -emit-llvm` output apart line by line. The method is side-by-side comparison: every
piece of C gets a piece of IR next to it.

**Part II — The Full IR Syntax (ch. 8–14).**
Systematic coverage of every syntactic construct. Each chapter opens by referring back to a concrete
example from Part I, so "what it is" always hangs off "what you have already seen".

**Part III — Writing a Lisp → LLVM IR Compiler (ch. 15–20).**
A real compiler in Python. Lisp is the source language because its S-expression syntax can be
explained in one page, leaving all your attention for IR generation.

**Appendices A–D.**
Where the differences from common claims live (A), an optimization primer (B), compiler
implementation notes (C), and an **LLVM IR instruction quick reference** (D).

## Every claim is verified

This book's central promise is that **the text matches reality**. Concretely:

- Every IR listing, error message, and number was produced by `clang-18` / `llvm-as-18` / `opt-18` /
  `llc-18` on **LLVM 18.1.3**.
- The Part III compiler really runs. Its 22 end-to-end tests pass, and each one compiles Lisp to IR,
  **verifies the IR with the LLVM verifier**, links it against a C driver, and compares the output.
- Where a widely repeated claim disagrees with the toolchain (for example the "three-line IR" story,
  or `opt -passname` syntax), the book says so and shows the real output.

You can re-run all of it:

```bash
bash audit/run_all.sh
```

That runs six independent checks: toolchain version, IR snippets against live output, **re-derivation
of comparative claims**, reproduction of every quoted error message, verbatim matching of generated
code, and the full 22-case test suite.

```
ALL BOOK IR SNIPPETS MATCH LIVE OUTPUT
ALL COMPARATIVE CLAIMS RE-DERIVED AND CORRECT
ALL QUOTED ERROR MESSAGES REPRODUCE EXACTLY
ALL SAMPLED COMPILER OUTPUTS APPEAR VERBATIM IN THE BOOK
ALL LINKS AND ANCHORS RESOLVE
22/22 passed
```

## Layout

```
book-zh/     Chinese edition (25 files: preface, 20 chapters, 4 appendices)
book-en/     English edition (same structure)
code/
├── part1-c/        C sources for Part I
├── part2-ir/       hand-written .ll for Part II (3 are deliberately invalid)
├── part3-lispc/    the compiler from Part III
└── extra/          C driver files
audit/       the verification scripts behind the numbers above
```

See [`code/README.md`](code/README.md) for a per-file index mapping each source file to its chapter.

## Requirements

```
clang-18 / llvm-as-18 / opt-18 / llc-18 / lli-18   (LLVM 18.1.3)
python3                                            (3.12)
```

On Ubuntu:

```bash
sudo apt install clang-18 llvm-18 llvm-18-tools
clang-18 --version    # expect 18.1.3
```

**LLVM IR changes between releases.** Pointer syntax, `opt` command-line syntax, and floating-point
constant formatting all differ across versions. If your output disagrees with the book, trust your
terminal and check your version.

## Building the compiler, end to end

```bash
cd code/part3-lispc
python3 tests.py                       # 22/22
python3 compiler.py examples/fib.lisp   # print the generated IR
```

## License

[MIT](LICENSE) for the text and all code in this repository.
