#!/usr/bin/env python3
"""Cross-check the flagship IR snippets quoted in the book against live output.

For each claim we regenerate the IR from the C/Lisp source and assert that the
key lines the book quotes are present verbatim.
"""
import os, re, subprocess, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, "code")
LISPC = os.path.join(ROOT, "code", "part3-lispc")

def clang_ir(cfile, opt):
    src = os.path.join(VERIFY, "part1-c", cfile)
    r = subprocess.run(["clang-18", "-S", "-emit-llvm", f"-{opt}", src, "-o", "-"],
                       capture_output=True, text=True)
    return r.stdout

def lisp_ir(lfile):
    r = subprocess.run([sys.executable, "compiler.py", os.path.join("examples", lfile)],
                       capture_output=True, text=True, cwd=LISPC)
    return r.stdout

FAILS = []
def check(label, haystack, needles):
    for n in needles:
        if n not in haystack:
            FAILS.append(f"{label}: MISSING {n!r}")

# ---- Chapter 2: mul_add ----
o0 = clang_ir("mul_add.c", "O0")
o2 = clang_ir("mul_add.c", "O2")
check("ch2 mul_add -O0", o0, [
    "define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2)",
    "%4 = alloca i32, align 4",
    "store i32 %0, ptr %4, align 4",
    "%9 = mul nsw i32 %7, %8",
    "%11 = add nsw i32 %9, %10",
    "ret i32 %11",
])
n0 = len([l for l in o0.splitlines() if re.match(r'\s+%?\w*\s*=?\s*(alloca|store|load|mul|add|ret)', l.strip())])
check("ch2 mul_add -O2", o2, [
    "%4 = mul nsw i32 %1, %0",
    "%5 = add nsw i32 %4, %2",
    "ret i32 %5",
])
assert o0.count("\n") > 0
print(f"  ch2: -O0 body has {len([l for l in o0.splitlines() if l.startswith('  ') and not l.startswith('  ;')])} instruction lines (book claims 12)")

# ---- Chapter 4: comparisons / logic ----
cmp_ir = clang_ir("cmp.c", "O2")
check("ch4 cmp", cmp_ir, [
    "icmp slt i32", "icmp sle i32", "icmp sgt i32",
    "icmp sge i32", "icmp eq i32", "icmp ne i32", "icmp ult i32",
    "zext i1", 
])
bool_ir = clang_ir("bool.c", "O0")
check("ch4 &&/||", bool_ir, [
    "phi i1 [ false, %2 ], [ %9, %7 ]",
    "phi i1 [ true, %2 ], [ %9, %7 ]",
    "xor i1 %4, true",
])

# ---- Chapter 5: phi / select / switch ----
tern0 = clang_ir("ternary.c", "O0")
tern2 = clang_ir("ternary.c", "O2")
check("ch5 ternary -O0", tern0, ["%14 = phi i32 [ %10, %9 ], [ %12, %11 ]"])
check("ch5 ternary -O2", tern2, ["select i1 %4, i32 %2, i32 %1"])
sw2 = clang_ir("switcher.c", "O2")
check("ch5 switch -O2", sw2, ["@switch.table.switcher", "phi i32 [ %6, %3 ], [ -1, %1 ]"])

# ---- Chapter 6: gep ----
agg = clang_ir("agg.c", "O0")
check("ch6 struct gep", agg, [
    "%struct.Point = type { i32, i32 }",
    "getelementptr inbounds %struct.Point, ptr %3, i32 0, i32 1",
    "getelementptr inbounds %struct.Point, ptr %6, i32 0, i32 0",
])
check("ch6 array gep", agg, ["getelementptr inbounds i32, ptr %12, i64 %14", "sext i32 %13 to i64"])

# ---- Chapter 7: functions ----
fn0 = clang_ir("funcs.c", "O0")
check("ch7 declare/call", fn0, [
    "declare i32 @add(i32 noundef, i32 noundef)",
    "%10 = call i32 %7(i32 noundef %8, i32 noundef %9)",
    "%13 = phi i32 [ 1, %5 ], [ %11, %6 ]",
    "define internal i32 @helper",
])

# ---- Chapter 9: types ----
ty = clang_ir("types.c", "O0")
check("ch9 type mapping", ty, [
    "@f_char(i8 noundef signext %0)", "@f_uchar(i8 noundef zeroext %0)",
    "@f_short(i16 noundef signext %0)", "@f_ushort(i16 noundef zeroext %0)",
    "@f_int(i32 noundef %0)", "@f_uint(i32 noundef %0)",
    "@f_long(i64 noundef %0)", "@f_ll(i64 noundef %0)",
    "@f_bool(i1 noundef zeroext %0)", "@f_float(float noundef %0)",
    "@f_double(double noundef %0)", "@f_ld(x86_fp80 noundef %0)",
    "@f_ptr(ptr noundef %0)", "@f_arr(ptr noundef %0)",
])

# ---- Chapter 10: constants ----
co = clang_ir("consts.c", "O0")
check("ch10 float/string consts", co, [
    "ret double 1.000000e+00", "ret double 1.000000e-01",
    "ret double 5.000000e-01", "ret double 2.500000e-01",
    '@.str = private unnamed_addr constant [6 x i8] c"hello\\00", align 1',
])

# ---- Chapter 3: fold / strength reduction ----
fold = clang_ir("fold.c", "O2")
check("ch3 fold", fold, [
    "define dso_local noundef i32 @f(i32 noundef %0) local_unnamed_addr #0 {\n  ret i32 1",
    "shl nsw i32 %0, 1", "mul nsw i32 %0, 3", "shl nsw i32 %0, 2", "mul nsw i32 %0, 5",
    "sub i32 0, %0",
    "ashr i32 %0, 3", "lshr i32 %0, 3",
])

# ---- Part III: generated IR ----
fib = lisp_ir("fib.lisp")
check("ch19 fib", fib, [
    "define i32 @l_fib(i32 %n)",
    "%t1 = icmp slt i32 %n, 2",
    "br i1 %t1, label %then1, label %else2",
    "%t7 = phi i32 [ %n, %then1 ], [ %t6, %else2 ]",
    "%t3 = call i32 @l_fib(i32 %t2)",
])
sm = lisp_ir("sum.lisp")
check("ch18/20 sum", sm, [
    "%i.addr = alloca i32, align 4", "%s.addr = alloca i32, align 4",
    "br label %while.cond1", "br i1 %t2, label %while.body2, label %while.end3",
])
if "phi" in sm:
    FAILS.append("ch18 sum: book claims ZERO phi in generated sum_to, but found one")

print()
if FAILS:
    print(f"{len(FAILS)} MISMATCH(ES):")
    for f in FAILS: print("   ", f)
    sys.exit(1)
print("ALL BOOK IR SNIPPETS MATCH LIVE OUTPUT")

# ---------------------------------------------------------------------------
# Numeric-claim audit: counts the book states explicitly must match reality.
# ---------------------------------------------------------------------------
print("\n--- numeric claims ---")
body = [l for l in o0.splitlines() if l.startswith("  ") and not l.startswith("  ;")]
book_says_o0 = 12
print(f"  ch2 mul_add -O0 instruction lines: actual={len(body)} book={book_says_o0}",
      "OK" if len(body) == book_says_o0 else "MISMATCH")
if len(body) != book_says_o0:
    sys.exit(1)

body2 = [l for l in o2.splitlines() if l.startswith("  ") and not l.startswith("  ;")]
book_says_o2 = 3
print(f"  ch2 mul_add -O2 instruction lines: actual={len(body2)} book={book_says_o2}",
      "OK" if len(body2) == book_says_o2 else "MISMATCH")

# sum_to: 3 alloca / 6 load / 5 store / 0 phi before mem2reg; 0/0/0 / 2 phi after
def counts(ir):
    return dict(
        alloca=len(re.findall(r'alloca', ir)),
        load=len(re.findall(r'\bload\b', ir)),
        store=len(re.findall(r'\bstore\b', ir)),
        phi=len(re.findall(r'\bphi\b', ir)),
    )
pre = counts(sm)
import subprocess as sp
m2r = sp.run(["opt-18", "-passes=mem2reg", "-S", "-o", "-"], input=sm,
             capture_output=True, text=True).stdout
post = counts(m2r)
print(f"  ch20 sum_to before mem2reg: {pre}  book claims alloca=3 load=6 store=5 phi=0")
print(f"  ch20 sum_to after  mem2reg: {post}  book claims alloca=0 load=0 store=0 phi=2")
assert pre == dict(alloca=3, load=6, store=5, phi=0), pre
assert post == dict(alloca=0, load=0, store=0, phi=2), post
print("  numeric claims verified")
