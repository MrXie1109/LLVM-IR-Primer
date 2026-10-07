# 本书配套源码 / Source code for the book

本目录收录《LLVM IR Primer：从 C 到 Lisp 的完整指南》中出现的全部源码，按书中位置组织，方便对照与查询。

This directory holds every source file that appears in *LLVM IR Primer: From C to Lisp*, organised
by where the book uses it. The Chinese edition is under `book-zh/`, the English edition under
`book-en/`; this `code/` tree serves both — the code is identical, only the surrounding prose differs.

> **英文读者注意**：章节编号与中文版一致（第 N 章 = Chapter N）。下表用「第 N 章 / Chapter N」标注。
> **English readers:** section numbers match the Chinese edition. Table entries are marked
> "第 N 章 / Chapter N".

**环境**：LLVM 18.1.3（`clang-18` / `llvm-as-18` / `opt-18` / `llc-18` / `lli-18`）+ Python 3。

```
code/
├── part1-c/        第一部分（第 1–7 章）：C 源码
├── part2-ir/       第二部分（第 8–14 章）：手写 .ll
├── part3-lispc/    第三部分（第 15–20 章）：Lisp 编译器
└── extra/          书中示例用到的 C 驱动与测试文件
```

---

## part1-c —— 第一部分：C 源码

用 `clang-18 -S -emit-llvm -O0 <file> -o -` 即可复现书中的 IR。
（多数例子同时给出 `-O2`，把 `-O0` 换成 `-O2` 即可。）

| 文件 | 对应章节 | 内容 |
|---|---|---|
| `mul_add.c` | 第 2 章 | 全书锚点：`int mul_add(int x,int y,int z)` |
| `two.c`、`three.c`、`numtest.c` | 第 2、8 章 | 编号规则（`%3` 去哪了、匿名块占号） |
| `arith.c` | 第 3 章 | 加减乘除、取余、取负、按位取反 |
| `logic.c` | 第 3 章 | `&` `\|` `^` 与三种移位 |
| `fold.c` | 第 3 章 | `nsw` 的价值：`x+1>x` 被折叠、强度削弱 |
| `div4.c` | 附录 B | 有符号除法不能变移位，无符号可以 |
| `cmp.c` | 第 4 章 | 7 种 `icmp` 谓词 |
| `bool.c` | 第 4 章 | `&&` `\|\|` `!` 与短路求值 |
| `side_effect.c` | 第 4 章 | 为什么有副作用时 `&&` **不能**折叠成 `and i1` |
| `ptrbool.c` | 第 4 章 | 指针真值、`fcmp` 谓词、NaN |
| `ternary.c` | 第 5 章 | `?:` → `phi`（`-O0`）vs `select`（`-O2`） |
| `ctrl.c` | 第 5 章 | `if`/`else`、`for` 循环、`abs` 变内建 |
| `switcher.c` | 第 5 章 | `switch` → 查表 |
| `safediv.c` | 第 5 章 | 为什么这里不能用 `select` |
| `classify.c` | 第 5 章 | 嵌套 `if` 的块结构 |
| `agg.c` | 第 6 章 | 结构体字段 GEP、数组索引 |
| `gelem.c` | 第 6 章 | `a[i]` 的 `sext` + GEP |
| `mem.c` | 第 6 章 | 全局变量、`static`、`const`、`extern` |
| `use_ext.c` | 第 6 章 | 使用 `extern` 变量，`@g_ext` 才会出现在 IR 里 |
| `packed.c` | 第 6 章 | 打包结构体 `<{ ... }>` |
| `deref.c` | 第 6 章 | 指针解引用 |
| `funcs.c` | 第 7 章 | 函数声明、函数指针、递归、`static` |
| `varargs.c` | 第 7 章 | 变参函数与 `llvm.va_start` |
| `attrs.c` | 第 7、12 章 | `noinline`、`always_inline`、`noreturn` |
| `fastc.c` | 第 7 章 | `fastcc` 出现在 `internal` 函数上 |
| `types.c` | 第 9 章 | C 类型 → IR 类型完整映射 |
| `consts.c`、`consts2.c` | 第 10 章 | 浮点常量打印、字符串字面量 |
| `conv.c` | 第 11 章 | 各类转换指令 |
| `cast.c` | 第 11 章 | `sext`/`trunc`/`zext` |
| `sum3.c` | 第 11 章 | `-ffast-math` 产生的 `fadd fast` |
| `atom.c` | 第 11 章 | `volatile` 与 `atomicrmw` |
| `add_arrays.c` | 第 12 章 | `restrict` → `noalias`（`dst[i] += a[i]`，**既读又写**，故无 `writeonly`） |
| `restrict.c`、`norestrict.c` | 第 12 章 | `copy`（`dst[i] = src[i]`，只写 → 带 `writeonly`）与去掉 `restrict` 的对照 |
| `meta.c` | 第 12 章 | 调试元数据（配合 `-g`） |
| `optdemo.c` | 第 13 章 | `mem2reg` 与 `-O2` 的观察对象 |
| `linker.c` | 第 7 章 | `declare` 与外部符号 |

**注意 `-O0` 与 `-O2` 差异极大。** 书中的「三行 IR」指 `-O2`；`-O0` 下 `mul_add` 的函数体有 12 条指令。

---

## part2-ir —— 第二部分：手写 `.ll`

| 文件 | 对应章节 | 内容 |
|---|---|---|
| `types.ll` | 第 9 章 | 全部基本类型与聚合类型 |
| `insts.ll` | 第 11 章 | 各类指令语法 |
| `gep.ll` | 第 6 章 | GEP：结构体字段、数组元素、负索引 |
| `cfg.ll` | 第 5 章 | 手写 `phi`：`max_via_phi`、`loop_phi` |
| `linkage.ll` | 第 10 章 | 全部链接属性 |
| `misc.ll` | 第 10、12 章 | 全局变量、属性组、模块标志 |
| `intr.ll`、`intr2.ll` | 第 12 章 | 内建函数（`memcpy`、`ctpop`、`smax`） |
| `poison.ll` | 第 10 章 | `poison` 与 `freeze` |
| `typedptr.ll` | 附录 A | 旧式类型化指针被静默改写为 `ptr` |
| `num2.ll` | 第 8 章 | 编号值配匿名块 |
| **`numfail.ll`** | 第 8、17 章、附录 C | **故意非法**：编号值倒退 |
| **`bad_dom.ll`** | 第 14 章 | **故意非法**：定义不支配使用 |
| **`bad_phi.ll`** | 第 5 章 | **故意非法**：`phi` 前驱不匹配 |
| **`bad_term.ll`** | 第 14 章 | **故意非法**：终结指令后还有指令 |

**加粗的四个文件是刻意写错的**，用来复现书中的验证器报错。它们**应当**被 `llvm-as-18` 拒绝：

```bash
llvm-as-18 bad_phi.ll -o /dev/null     # 预期报错
```

其余文件都可以通过验证：

```bash
for f in *.ll; do llvm-as-18 "$f" -o /dev/null && echo "OK  $f"; done
```

---

## part3-lispc —— 第三部分：Lisp → LLVM IR 编译器

| 文件 | 行数 | 职责 |
|---|---|---|
| `lexer.py` | ~100 | 词法分析：文本 → token |
| `reader.py` | ~130 | 语法分析：token → S-表达式 |
| `ir.py` | ~430 | IR 构建器：`Block`/`Function`/`Module` |
| `compiler.py` | ~490 | 代码生成：S-表达式 → IR |
| `tests.py` | ~400 | 端到端测试（22 个用例） |
| `minimal_codegen.py` | ~100 | 第 14 章的最小骨架 |
| `examples/*.lisp` | — | 示例程序 |

### 快速上手

```bash
cd part3-lispc

# 编译一个 Lisp 程序，看它生成的 IR
python3 compiler.py examples/fib.lisp

# 验证生成的 IR（会运行 LLVM 验证器）
python3 compiler.py examples/fib.lisp > fib.ll
llvm-as-18 fib.ll -o fib.bc

# 跑完整测试套件（需要 clang-18 和 llvm-as-18）
python3 tests.py
```

### 示例程序

| 文件 | 内容 | 用到的 IR 特性 |
|---|---|---|
| `fib.lisp` | 递归斐波那契 | `call`、`phi`、嵌套 `br` |
| `sum.lisp` | `while` 循环求和 | `alloca`、`load`/`store`、回边 |
| `countdown.lisp` | 尾递归倒数 | 测试 LLVM 能否消除尾调用 |
| `tailacc.lisp` | 带累加器的尾递归 | `tailcallelim` → 循环 → 闭式公式 |

### 语言速览

```lisp
(defn name (params...) body...)   ; 函数定义
(declare name (i32 ...))          ; 外部函数声明
(defg name init)                  ; 全局变量
(let ((v e)...) body...)          ; 局部绑定（顺序求值）
(set v e)                         ; 赋值
(if cond then else)               ; 条件表达式，产出值
(while cond body...)              ; 循环，产出 0
(+ - * / %)                       ; 算术
(< <= > >= = !=)                  ; 比较（产出 i1）
(f args...)                       ; 调用
```

**明确的边界**：不支持闭包、嵌套函数、动态类型、GC、尾调用优化。理由见第 15 章。

---

## extra —— C 驱动与测试文件

书中的第三部分例子需要把生成的 `.bc` 和 C 驱动链接起来才能运行。

| 文件 | 用途 |
|---|---|
| `driver_fib.c` | 调用编译器生成的 `l_fib`（第 19 章） |
| `driver_sum.c` | 调用 `l_sum_to`，验证 `-O2` 结果（第 20 章） |
| `driver_abs.c` | 运行手写的 `loop_phi`（第 5 章） |
| `driver_tailacc.c` | 尾递归实验（第 15 章） |
| `intr_main.c` | 测试 `llvm.ctpop` / `llvm.smax`（第 12 章） |
| `overflow_main.c` | 测试 `llvm.sadd.with.overflow`（第 12 章） |
| `size_layout.c` | 打印结构体大小与字段偏移（第 9 章） |
| `ext_abs.c` | `extern_call` 测试用的外部函数实现（第 20 章） |

示例：

```bash
cd part3-lispc && python3 compiler.py examples/fib.lisp > fib.ll && llvm-as-18 fib.ll -o fib.bc
clang-18 -w ../extra/driver_fib.c fib.bc -o fibtest && ./fibtest
```

---

## 一个提醒

**所有 IR 输出都与 LLVM 18.1.3 绑定。** 换版本后输出可能显著不同（指针写法、`opt` 命令行语法、浮点常量格式都会变）。如果你的结果与书中不一致，请以你的终端为准，并检查版本：

```bash
clang-18 --version      # 应为 18.1.3
```
