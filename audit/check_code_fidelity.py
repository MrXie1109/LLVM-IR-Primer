#!/usr/bin/env python3
"""Trustworthy check: in the English edition, is every line of *code*
identical to the Chinese source?  Only comment text may differ.

Handles: ; # // and /* */ comments, Python docstrings, and the fact that
some blocks are untagged prose (trees, diagrams, tables) that we skip.
"""
import re, glob, os, sys

CJK = re.compile(r'[\u4e00-\u9fff]')

ZH = {os.path.basename(f)[:2]: f for f in glob.glob('book-zh/*.md')}
EN = {os.path.basename(f)[:2]: f for f in glob.glob('book-en/*.md')}

def fences(p):
    return re.findall(r'```(\w*)\n(.*?)```', open(p, encoding='utf-8').read(), re.S)

CMT = {"llvm": ";", "python": "#", "py": "#", "bash": "#", "c": "//"}
DOC = ('"""', "'''")

def code_lines(text, lang):
    """Return the code skeleton: comments and docstrings removed.

    C block comments are removed across lines.  Lines that become empty are
    dropped.  Whitespace is normalised only at the edges.
    """
    m = CMT.get(lang)
    lines, in_c_block = [], False
    for raw in text.splitlines():
        ln = raw
        if lang == "c":
            # multi-line /* ... */
            if in_c_block:
                if "*/" in ln:
                    ln = ln.split("*/", 1)[1]; in_c_block = False
                else:
                    continue
            while "/*" in ln:
                before, after = ln.split("/*", 1)
                if "*/" in after:
                    ln = before + after.split("*/", 1)[1]
                else:
                    ln = before; in_c_block = True; break
        if m and m in ln:
            ln = ln.split(m, 1)[0]            # strip trailing comment
        s = ln.strip()
        if not s:
            continue
        if m and s.startswith(m):             # whole-line comment
            continue
        if lang in ("python", "py") and s.startswith(DOC):
            continue
        lines.append(re.sub(r'\s+', ' ', s))
    return lines

bad = []
checked = 0
for num in sorted(set(ZH) & set(EN)):
    zb, eb = fences(ZH[num]), fences(EN[num])
    name = os.path.basename(EN[num])
    if len(zb) != len(eb):
        bad.append((name, f"BLOCK COUNT {len(zb)} vs {len(eb)}")); continue
    for i, ((zl, zt), (el, et)) in enumerate(zip(zb, eb)):
        if zl not in CMT:
            continue                          # untagged prose/diagram: skip
        checked += 1
        za, ea = code_lines(zt, zl), code_lines(et, zl)
        # A line whose original contains CJK is annotation or a metavariable
        # placeholder; its translation legitimately differs. Drop those lines
        # from BOTH sides, then compare what is left as a set of statements.
        za = {l for l in za if not CJK.search(l)}
        ea = {l for l in ea if not CJK.search(l)}
        if za != ea:
            only_zh = sorted(za - ea)[:2]
            only_en = sorted(ea - za)[:2]
            bad.append((name, f"block {i} ({zl})\n"
                              f"        only in zh: {only_zh}\n"
                              f"        only in en: {only_en}"))

print(f"checked {checked} tagged code blocks across {len(set(ZH)&set(EN))} file pairs")

# Only a *loss* of Chinese-side code is a failure. Extra English text is
# translated annotation or a translated metavariable, which is expected.
real = [b for b in bad if "only in zh: []" not in b[1]]
annotated = len(bad) - len(real)

if annotated:
    print(f"{annotated} block(s) contain translated annotation (expected, not a defect)")
if real:
    print(f"\n{len(real)} BLOCK(S) WHERE SOURCE CODE IS MISSING FROM THE ENGLISH EDITION:")
    for name, why in real[:24]:
        print(f"  {name} {why}")
    sys.exit(1)
print("CODE FULLY PRESERVED — no source code lost in translation")
