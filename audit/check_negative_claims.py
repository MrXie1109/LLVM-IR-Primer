#!/usr/bin/env python3
"""Negative-claim audit: the class of error my first audit could not catch.

The original audit asserted "expected string IS in toolchain output".
It could never catch a claim I *invented* without running anything,
because invented claims are absent from the toolchain but present in prose.

This script does the inverse: for a set of prose assertions of the form
"X equals/behaves like Y", it RE-DERIVES the truth and compares.

It is deliberately small and specific. Add a row whenever you write a
comparative claim; if you cannot express the check, that is a signal the
claim is not verifiable and should be softened in the text.
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LP = os.path.join(ROOT, "code", "part3-lispc")
BOOK = os.path.join(ROOT, "book-zh")
scratch = os.path.join(ROOT, "review_scratch")
os.makedirs(scratch, exist_ok=True)

def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                          text=True, **kw)

def lisp_to_ir(example):
    r = sh([sys.executable, "compiler.py", f"examples/{example}"], cwd=LP)
    return r.stdout

def opt(ir, pipeline):
    r = sh(["opt-18", f"-passes={pipeline}", "-S", "-o", "-"], input=ir)
    return r.stdout

fails = []

# ---- CLAIM 1: ch20 says our -O2 output keeps the loop (not公式化), whereas
#      clang's eliminates it. Verify BOTH halves; the original text claimed
#      the opposite and my old audit happily passed.
ours = opt(lisp_to_ir("sum.lisp"), "default<O2>")
clang_ir = sh(["clang-18", "-S", "-emit-llvm", "-O2",
               os.path.join(ROOT, "code", "part1-c", "optdemo.c"), "-o", "-"]).stdout
ours_fn = re.search(r'define i32 @l_sum_to.*?\n\}', ours, re.S).group(0)
clang_fn = re.search(r'define dso_local i32 @sum_to.*?\n\}', clang_ir, re.S).group(0)

ours_has_loop = "phi" in ours_fn and "br i1" in ours_fn
clang_has_i33 = "i33" in clang_fn
print(f"CLAIM 1a: our -O2 output keeps the loop .......... {'loop present' if ours_has_loop else 'NO LOOP'}")
print(f"CLAIM 1b: clang -O2 formula-ises it (uses i33) ... {'i33 present' if clang_has_i33 else 'NO i33'}")
if not ours_has_loop:
    fails.append("ch20: text says our loop survives -O2, but it was eliminated")
if not clang_has_i33:
    fails.append("ch20: text says clang formula-ises, but no i33 found")

# ---- CLAIM 2: adding mustprogress DOES make our -O2 match clang's shape
mp = re.sub(r'^define i32 @l_sum_to\(i32 %n\) \{',
            'define i32 @l_sum_to(i32 %n) mustprogress nounwind willreturn {',
            lisp_to_ir("sum.lisp"), flags=re.M)
mp_o2 = opt(mp, "default<O2>")
mp_has_i33 = "i33" in mp_o2
print(f"CLAIM 2 : mustprogress makes our -O2 use i33 ...... {'yes' if mp_has_i33 else 'NO'}")
if not mp_has_i33:
    fails.append("ch20: text claims mustprogress enables formula-isation; not observed")

# ---- CLAIM 3: ch2 instruction count (the number the whole ch2 hinges on)
o0 = sh(["clang-18","-S","-emit-llvm","-O0",
         os.path.join(ROOT,"code","part1-c","mul_add.c"),"-o","-"]).stdout
body = re.search(r'define dso_local i32 @mul_add.*?\n\}', o0, re.S).group(0)
n = len([l for l in body.splitlines() if l.startswith("  ") and not l.startswith("  ;")])
book_text = open(os.path.join(BOOK, "02-第2章-mul_add.md")).read()
m = re.search(r'\*\*函数体里有 (\d+) 条指令\*\*', book_text)
book_n = int(m.group(1)) if m else -1
print(f"CLAIM 3 : ch2 says {book_n} instructions, actual {n} ..... {'OK' if book_n==n else 'MISMATCH'}")
if book_n != n:
    fails.append(f"ch2: book says {book_n} instructions, actual {n}")

# ---- CLAIM 4: ch10 visibility syntax must be a PREFIX, and the book's
#      negative example (comma form) must genuinely fail.
ok_prefix = sh(["llvm-as-18","-o","/dev/null","-"], input="@v = protected global i32 1\n").returncode == 0
bad_comma = sh(["llvm-as-18","-o","/dev/null","-"], input='@v = global i32 1, visibility protected\n').returncode != 0
print(f"CLAIM 4 : visibility is a prefix ({ok_prefix}), comma form invalid ({bad_comma})")
if not (ok_prefix and bad_comma):
    fails.append("ch10: visibility syntax claim wrong")
if "visibility protected" in book_text:
    fails.append("ch10: stale 'visibility protected' comma form still in prose")

print()
if fails:
    print(f"{len(fails)} NEGATIVE-CLAIM FAILURE(S):")
    for f in fails: print("   ", f)
    sys.exit(1)
print("ALL COMPARATIVE CLAIMS RE-DERIVED AND CORRECT")
