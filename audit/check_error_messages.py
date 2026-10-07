#!/usr/bin/env python3
"""Verify every quoted error message actually reproduces."""
import os, re, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "review_scratch", "errcheck"); os.makedirs(S, exist_ok=True)
fails = []

def asm(name, text):
    p = os.path.join(S, name)
    open(p, "w").write(text)
    r = subprocess.run(["llvm-as-18", p, "-o", "/dev/null"], capture_output=True, text=True)
    return (r.stderr or "") + (r.stdout or "")

# each: (label, ll source, substring the book quotes)
CASES = [
 ("undefined value",
  'define i32 @f() {\nentry:\n  %a = add i32 1, 2\n  ret i32 %b\n}\n',
  "use of undefined value '%b'"),
 ("phi predecessor mismatch",
  'define i32 @f(i32 %a, i32 %b) {\nentry:\n  %c = icmp sgt i32 %a, %b\n'
  '  br i1 %c, label %t, label %f\nt:\n  br label %m\nf:\n  br label %m\n'
  'm:\n  %r = phi i32 [ %a, %t ], [ %b, %entry ]\n  ret i32 %r\n}\n',
  "PHI node entries do not match predecessors!"),
 ("non-dominating use",
  'define i32 @f(i32 %a, i1 %cond) {\nentry:\n  br i1 %cond, label %t, label %f\n'
  't:\n  %x = add i32 %a, 1\n  br label %m\nf:\n  br label %m\n'
  'm:\n  %y = add i32 %x, 1\n  ret i32 %y\n}\n',
  "Instruction does not dominate all uses!"),
 ("missing terminator",
  'define i32 @f(i32 %a) {\nentry:\n  %x = add i32 %a, 1\n}\n',
  "expected instruction opcode"),
 ("instruction after terminator",
  'define i32 @f() {\nentry:\n  ret i32 0\n  %x = add i32 1, 2\n}\n',
  "expected instruction opcode"),
 ("numbering regression",
  'define i32 @f(i32 %x) {\nentry:\n  %1 = icmp eq i32 %x, 0\n'
  '  br i1 %1, label %2, label %3\n2:\n  %5 = add i32 %x, 1\n  ret i32 %5\n'
  '3:\n  %4 = sub i32 %x, 1\n  ret i32 %4\n}\n',
  "expected to be numbered"),
 ("digit-leading name",
  'define i32 @f(i32 %x) {\nentry:\n  %1abc = add i32 %x, 1\n  ret i32 %1abc\n}\n',
  "expected '=' after instruction id"),
 ("gep wrong type",
  '%struct.Point = type { i32, i32 }\ndefine i32 @f(ptr %p) {\n'
  '  %v = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1\n'
  '  ret i32 %v\n}\n',
  "defined with type 'ptr' but expected 'i32'"),
 ("trunc nsw invalid",
  'define i8 @f(i32 %x) {\n  %r = trunc nsw i32 %x to i8\n  ret i8 %r\n}\n',
  "expected type"),
 ("visibility comma form invalid",
  '@v = global i32 1, visibility protected\n',
  "unknown global variable property!"),
 ("type mismatch named vs literal",
  '%A = type { i32, i32 }\ndefine %A @f({ i32, i32 } %x) {\n  ret %A %x\n}\n',
  "defined with type"),
]
print("quoted error messages:")
for label, src, want in CASES:
    got = asm("t.ll", src)
    ok = want in got
    print(f"  {'OK  ' if ok else 'FAIL'} {label:34} expects {want!r}")
    if not ok:
        fails.append((label, want, got.strip().splitlines()[0] if got.strip() else "(no output)"))

# opt legacy syntax must be rejected (ch13 claim)
r = subprocess.run(["opt-18", "-mem2reg", "-S", os.path.join(S,"t.ll")],
                   capture_output=True, text=True)
legacy_ok = "not supported" in (r.stderr or "")
print(f"  {'OK  ' if legacy_ok else 'FAIL'} opt legacy -passname rejected")
if not legacy_ok: fails.append(("opt legacy", "not supported", r.stderr[:120]))

print()
if fails:
    print(f"{len(fails)} ERROR-MESSAGE MISMATCH(ES):")
    for l,w,g in fails: print(f"   {l}: wanted {w!r}, got {g!r}")
    sys.exit(1)
print("ALL QUOTED ERROR MESSAGES REPRODUCE EXACTLY")
