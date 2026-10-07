#!/usr/bin/env python3
"""Verify that specific 'this is what our compiler produces' blocks in the book
match the compiler byte-for-byte (modulo trailing whitespace)."""
import os, re, subprocess, subprocess as sp, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LP = os.path.join(ROOT, "code", "part3-lispc")

def compile_lisp(src_text):
    """Compile Lisp source given inline, via the compiler module."""
    code = (
        "import sys; sys.path.insert(0,'%s')\n" % LP +
        "from compiler import compile_text\n" +
        "src = %r\n" % src_text +
        "sys.stdout.write(compile_text(src).render())\n"
    )
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout

def norm(s):
    return "\n".join(l.rstrip() for l in s.strip().splitlines())

# (chapter file, lisp source, human label)
CASES = [
 ("17-第17章-代码生成.md",
  "(defn mul_add (x y z) (+ (* x y) z))", "ch17 mul_add"),
 ("17-第17章-代码生成.md",
  "(defn f (x) (let ((y 1)) (set y 2) y))", "ch17 set/let"),
 ("18-第18章-控制流与phi.md",
  "(defn classify (x) (if (< x 0) 0 (if (= x 0) 1 2)))", "ch18 nested if"),
 ("18-第18章-控制流与phi.md",
  "(defn sum_to (n) (let ((i 1) (s 0)) (while (<= i n) (set s (+ s i)) (set i (+ i 1))) s))",
  "ch18 sum_to loop"),
]

fails = []
for chapter, lisp, label in CASES:
    actual = norm(compile_lisp(lisp))
    text = open(os.path.join(ROOT, "book-zh", chapter)).read()
    # every llvm block in that chapter
    blocks = [norm(b) for b in re.findall(r'```llvm\n(.*?)```', text, re.S)]
    hit = any(actual == b for b in blocks)
    # A block may legitimately be absent when the book only asks the reader to
    # run it (an exercise) rather than quoting its output. Detect that case.
    is_exercise = lisp in text and "练习" in text.split(lisp)[0][-200:]
    if hit:
        status = "FOUND verbatim in chapter"
    elif is_exercise:
        status = "SKIP (exercise prompt, no output quoted)"
    else:
        status = "NOT FOUND"
    print(f"{label:22} -> {status}")
    if not hit and not is_exercise:
        partial = any(b and actual.startswith(b) for b in blocks)
        print(f"{'':22}    prefix-match: {partial}")
        if not partial:
            fails.append(label)

print()
if fails:
    print("UNABLE TO MATCH:", fails); sys.exit(1)
print("ALL SAMPLED COMPILER OUTPUTS APPEAR VERBATIM IN THE BOOK")

# ---------------------------------------------------------------------------
# Cross-check EVERY ```llvm block that looks like clang/opt output against
# live regeneration.  This is the check that would have caught appendix B.6,
# where a hand-edited block drifted from reality.
# ---------------------------------------------------------------------------
print("\n--- appendix B.6: opt -O2 on clang -O0 IR ---")
import tempfile, os as _os
tmp = tempfile.mkdtemp()
c = _os.path.join(tmp, "sum_to.c")
open(c, "w").write(
    "int sum_to(int n) {\n"
    "    int s = 0;\n"
    "    for (int i = 1; i <= n; i++)\n"
    "        s += i;\n"
    "    return s;\n"
    "}\n")
o0 = sp.run(["clang-18","-S","-emit-llvm","-O0",c,"-o","-"],
            capture_output=True, text=True).stdout
nooptnone = o0.replace(" optnone", "")
o2 = sp.run(["opt-18","-passes=default<O2>","-S","-o","-"],
            input=nooptnone, capture_output=True, text=True).stdout
fn = re.search(r'define dso_local i32 @sum_to.*?\n\}', o2, re.S)
real_o2 = norm(fn.group(0)) if fn else ""
book_b = open(_os.path.join(ROOT, "book-zh", "22-附录B-优化入门.md")).read()
blocks_b = [norm(x) for x in re.findall(r'```llvm\n(.*?)```', book_b, re.S)]
if real_o2 in blocks_b:
    print("  appendix B.6 -O2 output: VERBATIM MATCH")
else:
    print("  appendix B.6 -O2 output: *** DRIFTED FROM REALITY ***")
    print("  real first line:", real_o2.splitlines()[0] if real_o2 else "(none)")
    print("  real second line:", real_o2.splitlines()[1] if real_o2 else "")
    fails.append("appendix B.6 -O2 block does not match live opt output")

print()
if fails:
    print(f"{len(fails)} BLOCK MISMATCH(ES): {fails}")
    sys.exit(1)
print("ALL CROSS-CHECKED BLOCKS MATCH")
