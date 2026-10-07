#!/usr/bin/env python3
"""Verify the English edition preserves every code block from the Chinese one.

For each translated pair, extract all fenced code blocks (excluding pure-prose
annotation comments) and check that code lines are identical between zh and en.
Chinese prose comments inside code are allowed to differ (they get translated).
"""
import re, os, glob, sys, difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZH = os.path.join(ROOT, "book-zh")
EN = os.path.join(ROOT, "book-en")

MAP = {
 "00-前言.md":"00-preface.md",
 "01-第1章-为什么学LLVM-IR.md":"01-ch01-why-learn-llvm-ir.md",
 "02-第2章-mul_add.md":"02-ch02-your-first-ir-mul-add.md",
 "03-第3章-算术逻辑移位.md":"03-ch03-arithmetic-logic-and-shifts.md",
 "04-第4章-比较与i1.md":"04-ch04-comparisons-and-i1.md",
 "05-第5章-控制流与phi.md":"05-ch05-control-flow-and-phi.md",
 "06-第6章-内存与getelementptr.md":"06-ch06-memory-and-getelementptr.md",
 "07-第7章-函数与调用.md":"07-ch07-functions-and-calls.md",
 "08-第8章-标识符与命名.md":"08-ch08-identifiers-and-naming.md",
 "09-第9章-类型系统.md":"09-ch09-the-type-system.md",
 "10-第10章-常量与全局变量.md":"10-ch10-constants-and-globals.md",
 "11-第11章-指令集详解.md":"11-ch11-instruction-reference.md",
 "12-第12章-属性元数据内建函数.md":"12-ch12-attributes-metadata-and-intrinsics.md",
 "13-第13章-优化管线与opt.md":"13-ch13-the-optimization-pipeline-and-opt.md",
 "14-第14章-从读到写.md":"14-ch14-from-reading-to-writing-ir.md",
 "15-第15章-目标语言与骨架.md":"15-ch15-language-design-and-skeleton.md",
 "16-第16章-词法与语法分析.md":"16-ch16-lexing-and-parsing.md",
 "17-第17章-代码生成.md":"17-ch17-code-generation.md",
 "18-第18章-控制流与phi.md":"18-ch18-control-flow-and-phi-nodes.md",
 "19-第19章-完整走读.md":"19-ch19-a-complete-walkthrough.md",
 "20-第20章-测试验证与优化.md":"20-ch20-testing-verification-and-optimization.md",
 "21-附录A-与常见说法的差异.md":"21-appendix-a-differences-from-common-claims.md",
 "22-附录B-优化入门.md":"22-appendix-b-optimization-primer.md",
 "23-附录C-编译器实现笔记.md":"23-appendix-c-compiler-implementation-notes.md",
 "24-附录D-指令速查表.md":"24-appendix-d-instruction-quick-reference.md",
}

def blocks(path):
    """Return {lang: [code_text, ...]} preserving order."""
    src = open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r'```(\w*)\n(.*?)```', src, re.S):
        out.append((m.group(1), m.group(2)))
    return out

TRIPLE_DQ = '"' * 3
TRIPLE_SQ = "'" * 3

def strip_zh_comments(text, lang):
    """Keep only *code* lines; drop anything that is purely a comment/docstring.

    Comment and docstring text is legitimately translated, so it must not be
    compared. What we DO compare is the executable skeleton: instruction
    mnemonics, operands, identifiers, punctuation.
    """
    COMMENTS = {
        "llvm": ";", "lisp": ";", "bash": "#", "diff": None,
        "python": "#", "py": "#", "c": "//",
    }
    marker = COMMENTS.get(lang, None)
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if marker and s.startswith(marker):          # whole-line comment
            continue
        if s.startswith(TRIPLE_DQ) or s.startswith(TRIPLE_SQ):   # docstring line
            continue
        if lang == "c" and (s.startswith("/*") or s.startswith("*") or s.startswith("*/")):
            continue
        if marker and marker in ln:                  # trailing inline comment
            ln = ln.split(marker)[0]
        ln = ln.rstrip()
        if ln.strip():
            lines.append(ln)
    return lines

CJK = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')

problems = []
checked = 0
for zh_name, en_name in sorted(MAP.items()):
    zp, ep = os.path.join(ZH, zh_name), os.path.join(EN, en_name)
    if not os.path.exists(ep):
        problems.append((en_name, "MISSING"))
        continue
    zb, eb = blocks(zp), blocks(ep)
    if len(zb) != len(eb):
        problems.append((en_name, f"block count differs: zh={len(zb)} en={len(eb)}"))
        continue
    for i, ((zl, zt), (el, et)) in enumerate(zip(zb, eb)):
        if zl != el:
            problems.append((en_name, f"block {i} lang differs: {zl!r} vs {el!r}"))
            continue
        if zl == "":        # plain fences: prose-ish, skip
            continue
        checked += 1
        zc = strip_zh_comments(zt, zl)
        ec = strip_zh_comments(et, zl)
        if zc != ec:
            d = list(difflib.unified_diff(zc, ec, lineterm="", n=0))[:8]
            problems.append((en_name, f"block {i} ({zl}) code differs:\n      " + "\n      ".join(d)))

print(f"compared {checked} code blocks across {len(MAP)} file pairs")
if problems:
    print(f"\n{len(problems)} PROBLEM(S):")
    for name, why in problems:
        print(f"  {name}: {why}")
    sys.exit(1)
print("ALL CODE BLOCKS PRESERVED IN TRANSLATION")
