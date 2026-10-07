#!/usr/bin/env python3
"""Translate the remaining Chinese annotation text inside code fences.

This handles two cases the chapter translators handled inconsistently:
  1. comment tails   ; 给 x 分配一块内存   ->  ; allocate space for x
  2. metavariables   <类型> <值>            ->  <type> <value>

Only comment text and angle-bracket metavariables are touched; code tokens are
never modified. A curated phrase table is used so the result is deterministic.
"""
import re, glob, os, sys

# Longest-first so multi-char phrases win.
PHRASES = [
 ("给 x 分配一块内存", "allocate space for x"),
 ("同一个变量被赋值两次", "the same variable is assigned twice"),
 ("有符号：ashr，结果是 -4", "signed: ashr, result is -4"),
 ("补符号位 1", "sign bit filled with 1"),
 ("非法：%result 在这条路径上", "illegal: %result on this path"),
 ("非法：又赋值一次！", "illegal: assigned a second time!"),
 ("错：%entry 不是 %m 的前驱", "wrong: %entry is not a predecessor of %m"),
 ("普通定义", "ordinary definition"),
 ("模块内可见", "visible within this module only"),
 ("只声明，不定义", "declared only, not defined"),
 ("有函数体 —— 定义", "has a body -- definition"),
 ("没有函数体 —— 声明", "no body -- declaration"),
 ("声明", "declaration"),
 ("被拒绝", "rejected"),
 ("十进制", "decimal"),
 ("八进制（前导 0）", "octal (leading 0)"),
 ("负数（iN 允许负数写法）", "negative (iN allows a leading minus)"),
 ("十六进制：必须带 u（无符号）或 s（有符号）前缀", "hex: requires a u (unsigned) or s (signed) prefix"),
 ("有符号十六进制", "signed hex"),
 ("浮点的十六进制位模式", "hex bit pattern for a float"),
 ("clang 打印 float 的常见格式", "the form clang prints for float"),
 ("p2：乘法换成左移", "p2: multiplication becomes a shift"),
 ("p3：不是 2 的幂，保持乘法", "p3: not a power of two, stays a multiply"),
 ("有符号：保持除法", "signed: stays a division"),
 ("无符号：变成逻辑右移", "unsigned: becomes a logical shift"),
 ("通用形式", "general form"),
 ("整数", "integer"),
 ("浮点", "floating point"),
 ("模块级信息", "module-level information"),
 ("类型定义", "type definitions"),
 ("全局变量", "global variables"),
 ("函数声明", "function declarations"),
 ("函数定义", "function definitions"),
 ("属性组", "attribute groups"),
 ("元数据", "metadata"),
 ("源码索引：每个文件对应哪一章", "source index: which chapter each file belongs to"),
 ("第一部分的 C 源码（37 个 .c）", "Part I C sources (37 .c files)"),
 ("第二部分的手写 .ll（14 个，含 3 个故意写错的）", "Part II hand-written .ll (14, 3 deliberately invalid)"),
 ("第三部分的编译器", "the Part III compiler"),
 ("词法分析", "lexer"),
 ("语法分析（S-表达式）", "parser (S-expressions)"),
 ("LLVM IR 构建器", "LLVM IR builder"),
 ("代码生成器", "code generator"),
 ("端到端测试（22 个用例）", "end-to-end tests (22 cases)"),
 ("第 14 章的最小骨架", "the minimal skeleton from Chapter 14"),
 ("Lisp 示例程序", "Lisp example programs"),
 ("书中示例用到的 C 驱动文件", "C driver files used by the book's examples"),
 ("源文件位于", "source file at"),
 # metavariables
 ("<类型>", "<type>"), ("<值>", "<value>"), ("<目标地址>", "<target address>"),
 ("<对齐>", "<alignment>"), ("<初始值>", "<initial value>"),
 ("<默认目标>", "<default target>"), ("<目标>", "<target>"),
 ("<行为>", "<behavior>"), ("<名字>", "<name>"),
 ("<函数名或 [module]>", "<function name or [module]>"),
 ("<pass 的类名>", "<pass class name>"),
 ("<类名>", "<class name>"), ("<函数名>", "<function name>"),
 ("<字段号>", "<field index>"), ("<元素>", "<element>"),
 ("<常量>", "<constant>"), ("<索引>", "<index>"), ("<计数>", "<count>"),
  # --- second pass: remaining annotation tails and mini-tables ---
 ("← 编号从 %6 倒退到 %4", "<- numbering goes backwards from %6 to %4"),
 ("← 从 5 退回到 2", "<- back from 5 to 2"),
 ("读出 x", "read x"),
 ("%r 是 poison", "%r is poison"),
 ("（补 0）", "(fills with 0)"),
 ("（补符号位 1）", "(fills the sign bit with 1)"),
 ("必须真的用它，否则 IR 里什么都不会有", "it must actually be used, or nothing appears in the IR"),
 ("一个 i32", "one i32"),
 ("10 个 i32（C 的 VLA）", "10 i32s (C's VLA)"),
 ("合法，但没有 inbounds", "legal, but without inbounds"),
 ("往前一个元素", "one element backwards"),
 ("单个 Point 的 y 字段", "the y field of a single Point"),
 ("第 3 个 Point 的 y 字段（p 是 Point 数组）", "the y field of the 3rd Point (p is an array of Point)"),
 ("%v 是 ptr，不是 i32", "%v is ptr, not i32"),
 ("← 类型错误：%v 是 ptr，不是 i32", "<- type error: %v is ptr, not i32"),
 ("命名值（named value）", "named value"),
 ("编号值（numbered / unnamed value）", "numbered / unnamed value"),
 ("命名值，与编号值混用", "named value, mixed with a numbered one"),
 ("参数 %0, %1, %2       → 计数器 = 3", "params %0, %1, %2      -> counter = 3"),
 ("入口块没有名字        → 占用 %3，计数器 = 4", "entry block unnamed    -> takes %3, counter = 4"),
 ("%4 = alloca ...       → 占用 %4，计数器 = 5", "%4 = alloca ...        -> takes %4, counter = 5"),
 ("store ...             → 不占号", "store ...              -> takes no number"),
 ("参数 %0               → 计数器 = 1", "param %0               -> counter = 1"),
 ("入口块没有名字        → 占用 %1，计数器 = 2", "entry block unnamed    -> takes %1, counter = 2"),
 ("%2 = alloca ...       → %2          ✓ 与实测一致", "%2 = alloca ...        -> %2          OK, matches measurement"),
 ("参数 %0, %1           → 计数器 = 2", "params %0, %1          -> counter = 2"),
 ("入口块没有名字        → 占用 %2，计数器 = 3", "entry block unnamed    -> takes %2, counter = 3"),
 ("%3 = alloca ...       → %3          ✓ 与实测一致", "%3 = alloca ...        -> %3          OK, matches measurement"),
 ("← 入口块有名字，不占编号", "<- the entry block is named, so it takes no number"),
 ("← 参数占了 %0，所以这里是 %1", "<- the parameter took %0, so this is %1"),
 ("← 匿名入口块占了 %1", "<- the anonymous entry block took %1"),
 ("以数字开头", "starts with a digit"),
 ("有空格", "contains a space"),
 ("%a 在 next 块里可见", "%a is visible in the next block"),
 ("# ← 危险！", "# <- dangerous!"),
 ("# 命名值，安全", "# named value, safe"),
 ("八进制（前导 0，和 C 一样）", "octal (leading 0, as in C)"),
 ("十六进制必须带 u（无符号）或 s（有符号）前缀", "hex requires a u (unsigned) or s (signed) prefix"),
 ("负数", "negative"),
 ("第 3 章", "Chapter 3"), ("第 5 章", "Chapter 5"), ("第 2 章", "Chapter 2"),
 ("是错的", "is wrong"), ("等等", "etc."),
]

CJK = re.compile(r'[\u4e00-\u9fff]')
changed_files = 0
for f in sorted(glob.glob('book-en/*.md')):
    if 'TRANSLATION_BRIEF' in f:
        continue
    src = open(f, encoding='utf-8').read()
    out, pos = [], 0
    n_before = 0
    for m in re.finditer(r'```(\w*)\n(.*?)```', src, re.S):
        n_before += len(CJK.findall(m.group(2)))
        body = m.group(2)
        for zh, en in PHRASES:
            body = body.replace(zh, en)
        out.append(src[pos:m.start()] + m.group(0)[:m.group(0).index('\n')+1] + body + "```")
        pos = m.end()
    out.append(src[pos:])
    new = "".join(out)
    n_after = sum(len(CJK.findall(mm.group(2)))
                  for mm in re.finditer(r'```(\w*)\n(.*?)```', new, re.S))
    if new != src:
        open(f, 'w', encoding='utf-8').write(new)
        changed_files += 1
        print(f"  {os.path.basename(f)}: {n_before} -> {n_after} CJK chars in fences")
print(f"\nrewrote {changed_files} files")
