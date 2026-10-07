# 第 6 章 内存、指针与 `getelementptr`

## 6.1 全局变量

先看最简单的：

```c
int g_counter = 42;
const int g_limit = 100;

int get_counter(void) { return g_counter; }
```

`-O0`：

```llvm
@g_counter = dso_local global i32 42, align 4
@g_limit = dso_local constant i32 100, align 4

define dso_local i32 @get_counter() #0 {
  %1 = load i32, ptr @g_counter, align 4
  ret i32 %1
}
```

几个要点：

1. **全局变量用 `@` 前缀**，函数也用 `@`。局部值用 `%`。
2. **`global` vs `constant`**：`const` 修饰的变量变成 `constant`。这不只是文档 —— 它向优化器承诺「这块内存不会被写」，因此可以被放进只读段，并且所有 `load` 都可以被常量传播。
3. **`align 4`**：对齐要求。
4. **`load i32, ptr @g_counter, align 4`** —— 全局变量的名字 `@g_counter` 本身就是一个**指针**（指向那块存储的地址），所以可以直接用作 `load` 的地址操作数，不需要先 `alloca`。

### `static` 和 `extern`

```c
int g_pub = 1;              /* 普通定义 */
static int s_hidden = 7;    /* 模块内可见 */
extern int g_ext;           /* 只声明，不定义 */
int use_ext(void) { return g_ext; }   /* 必须真的用它，否则 IR 里什么都不会有 */
```

```llvm
@g_pub = dso_local global i32 1, align 4
@s_hidden = internal global i32 7, align 4
@g_ext = external global i32, align 4

define dso_local i32 @use_ext() #0 {
  %1 = load i32, ptr @g_ext, align 4
  ret i32 %1
}
```

> **一个容易困惑的点**：如果源码里只有 `extern int g_ext;` 而**没有任何函数使用它**，clang 生成的 IR 里**不会有 `@g_ext` 这一行** —— 因为没有任何东西引用它，模块里也就不需要这个声明。上面的例子特意加了 `use_ext` 来让它出现。

| C | IR 链接属性 | 含义 |
|---|---|---|
| `static` | `internal` | 只在当前模块可见，链接器看不到 |
| `extern`（声明） | `external` | 在别处定义，本模块只引用 |
| 无修饰（定义） | （默认，即 `external`） | 本模块定义且对外可见 |

注意 `@g_ext = external global i32, align 4` **没有初始值** —— 因为它不在这里定义。

这也解释了第 7 章会讲的一个现象：`extern` 的全局变量和 `extern` 的函数一样，都会在模块里留下一个「待解析」的符号。

## 6.2 `alloca` 回顾与它的生命周期

第 2 章我们见过 `alloca`。这里补充几个要点。

```llvm
%p = alloca i32, align 4          ; 一个 i32
%q = alloca i32, i32 10, align 16 ; 10 个 i32（C 的 VLA）
```

`alloca` 的第二条形式带一个元素个数，用于可变长数组（VLA）。

**`alloca` 的生命周期是「函数返回时结束」。** 它分配在栈帧上，不需要（也不能）手动释放。这一点很重要：**IR 里没有 `free`**。你需要手动管理内存时，调用的是 C 的 `malloc`/`free`，而 `alloca` 是自动的。

在 `-O0` 下，所有 `alloca` 都集中在入口块的开头 —— 这不是语法要求（`alloca` 可以出现在任何块里），而是 clang 的代码生成策略，也是我们第三部分编译器的策略（第 17 章的 `alloca_slot`／`entry_allocas` 就是干这个的）。

## 6.3 `getelementptr`：LLVM IR 里最容易被误解的指令

`getelementptr` 通常缩写为 **GEP**。它做的事情只有一件：

> **计算一个地址，不做任何内存访问。**

这一点必须先刻进脑子。**GEP 不读内存，也不写内存，它只是做指针算术。** 读要用 `load`，写要用 `store`。

### 6.3.1 数组元素

```c
int get_elem(int *a, int i) { return a[i]; }
```

`-O0`：

```llvm
define dso_local i32 @get_elem(ptr noundef %0, i32 noundef %1) #0 {
  %3 = alloca ptr, align 8
  %4 = alloca i32, align 4
  store ptr %0, ptr %3, align 8
  store i32 %1, ptr %4, align 4
  %5 = load ptr, ptr %3, align 8
  %6 = load i32, ptr %4, align 4
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds i32, ptr %5, i64 %7
  %9 = load i32, ptr %8, align 4
  ret i32 %9
}
```

关键的三行：

```llvm
  %7 = sext i32 %6 to i64
  %8 = getelementptr inbounds i32, ptr %5, i64 %7
  %9 = load i32, ptr %8, align 4
```

- **`sext i32 %6 to i64`** —— C 的 `int` 是 32 位，但**指针算术在 64 位平台上用 64 位**。所以要先把索引从 `i32` 符号扩展到 `i64`。这个「无中生有」的转换很常见，看到 `sext` 紧跟 `getelementptr` 不要惊讶。
- **`getelementptr inbounds i32, ptr %5, i64 %7`** —— 计算 `%5 + %7 * sizeof(i32)`。
- **`load`** —— 真正把值读出来。

### 6.3.2 GEP 的参数读法

```llvm
getelementptr inbounds i32, ptr %5, i64 %7
              ^^^^^      ^^^^   ^^^^^^
              (1)        (2)    (3)
```

1. **`i32`（源元素类型）** —— 「把 `%5` 当成指向 `i32` 的指针」。
2. **`ptr %5`（基地址）** —— 从哪里开始算。
3. **`i64 %7`（索引）** —— 前进几个 `i32`。

**注意 `sizeof` 是自动的。** GEP 知道 `i32` 是 4 字节，所以 `%7 = 3` 意味着前进 12 字节。你**不需要**自己乘 4。

这正是 GEP 存在的理由：**它让指针算术与目标平台无关**。在 32 位平台上索引的宽度不同，`i32` 的对齐可能不同，但你的 GEP 代码不用改一行。

### 6.3.3 `inbounds`：一个必须理解的承诺

`inbounds` 的意思是：

> 「这个算术的结果仍然在原对象**内部**（或者恰好指向末尾的下一个位置）。如果不是，结果是 `poison`。」

这是一个**承诺**，像 `nsw` 一样。它给优化器权力：

- 既然不会跑出对象，那么「指针比较」就有确定的行为；
- 既然不会跑出对象，那么 `p + 1` 就不可能回绕（地址不会溢出）；
- 因此可以更自由地重排、合并、消除这些地址计算。

**代价是：如果你撒谎（真的跑出对象），行为未定义。** 在 C 里，数组越界本来就是 UB，所以 clang 可以放心地加 `inbounds`。

手写的 GEP **可以不加 `inbounds`**，这是合法的，只是优化机会少一些：

```llvm
%p = getelementptr i32, ptr %base, i64 %i     ; 合法，但没有 inbounds
```

**负索引也是合法的**：

```llvm
%r = getelementptr inbounds i32, ptr %base, i64 -1   ; 往前一个元素
```

### 6.3.4 结构体字段

这是 GEP 最容易让人困惑的地方，因为它需要**两个索引**。

```c
struct Point { int x; int y; };

int get_y(struct Point *p) { return p->y; }
void set_x(struct Point *p, int v) { p->x = v; }
```

`-O0`：

```llvm
%struct.Point = type { i32, i32 }

define dso_local i32 @get_y(ptr noundef %0) #0 {
  %2 = alloca ptr, align 8
  store ptr %0, ptr %2, align 8
  %3 = load ptr, ptr %2, align 8
  %4 = getelementptr inbounds %struct.Point, ptr %3, i32 0, i32 1
  %5 = load i32, ptr %4, align 4
  ret i32 %5
}

define dso_local void @set_x(ptr noundef %0, i32 noundef %1) #0 {
  %3 = alloca ptr, align 8
  %4 = alloca i32, align 4
  store ptr %0, ptr %3, align 8
  store i32 %1, ptr %4, align 4
  %5 = load i32, ptr %4, align 4
  %6 = load ptr, ptr %3, align 8
  %7 = getelementptr inbounds %struct.Point, ptr %6, i32 0, i32 0
  store i32 %5, ptr %7, align 4
  ret void
}
```

看那个双索引：

```llvm
%4 = getelementptr inbounds %struct.Point, ptr %3, i32 0, i32 1
                                              ^^^^^^  ^^^^^^
                                              (1)     (2)
```

**第一个索引 `i32 0`：** 这是**指针解引用步长**。它几乎总是 0，意思是「不要移动指针，就用它当前指的地方」。如果 `%3` 是 `struct Point` 的**数组**的指针，你想取第二个元素，这里就写 `i32 1`。

**第二个索引 `i32 1`：** 这是**结构体字段号**。`Point` 是 `{ i32, i32 }`，字段 0 是 `x`，字段 1 是 `y`。

所以整句读作：「把 `%3` 当作指向 `%struct.Point` 的指针，不移动它，取它的第 1 号字段」。

> **记忆法**：**第一个索引是「数组下标」，第二个是「字段号」。** 数组访问只需要第一个索引（并且通常是 `i64` 因为要符号扩展），结构体访问需要两个。

### 为什么要有第一个索引？

因为它让「数组的结构体」和「单个结构体」用同一条指令表达：

```llvm
; 单个 Point 的 y 字段
%a = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1

; 第 3 个 Point 的 y 字段（p 是 Point 数组）
%b = getelementptr inbounds %struct.Point, ptr %p, i64 3, i32 1
```

第二条里第一个索引变成了 `i64 3`，**索引的类型也从 `i32` 变成了 `i64`** —— 因为数组索引需要 64 位寻址能力。这个类型变化是 clang 的惯例（结构体字段号用 `i32` 足够，数组索引用 `i64`），不是语法要求。

### 6.3.5 `getelementptr` 常见错误的诊断

**错误一：以为 GEP 会读内存。**

```llvm
%v = getelementptr inbounds i32, ptr %p, i64 0   ; %v 是 ptr，不是 i32
```
GEP 的结果**永远是 `ptr`**（LLVM 18 里）。要拿到值必须再 `load`。

**错误二：忘了 `load`。**

```llvm
%v = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1
ret i32 %v        ; ← 类型错误：%v 是 ptr，不是 i32
```

```
llvm-as-18: error: '%v' defined with type 'ptr' but expected 'i32'
```

**错误三：以为索引是字节偏移。**

GEP 的索引是**元素**个数，不是字节数。`getelementptr i32, ptr %p, i64 1` 前进 4 字节，不是 1 字节。要按字节移动，得用 `i8` 作为元素类型。

## 6.4 数组

```c
int sum_arr(int *a, int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
```

`-O0` 的核心部分：

```llvm
11:                                               ; preds = %7
  %12 = load ptr, ptr %3, align 8
  %13 = load i32, ptr %6, align 4
  %14 = sext i32 %13 to i64
  %15 = getelementptr inbounds i32, ptr %12, i64 %14
  %16 = load i32, ptr %15, align 4
  %17 = load i32, ptr %5, align 4
  %18 = add nsw i32 %17, %16
  store i32 %18, ptr %5, align 4
  br label %19
```

`a[i]` → `sext` + `getelementptr inbounds i32, ptr %12, i64 %14` + `load`。和我们前面手写的完全一致。

## 6.5 结构体类型定义

注意 `%struct.Point = type { i32, i32 }` 这一行，它在函数之前：

```llvm
%struct.Point = type { i32, i32 }
```

这是**类型定义**，不是变量。`%struct.Point` 是一个**命名类型**。`{ i32, i32 }` 是**字面量类型**（匿名的结构体类型）。

LLVM 的命名规则：

- `%name` 开头的标识符，如果在模块级被 `= type` 定义，就是命名类型；
- `%struct.X` 是 clang 为 C 的 `struct X` 生成的惯用名字；
- `{ i32, i32 }` 是匿名结构体，可以内联使用，但每次写出都算同一个类型（结构类型相等是**结构等价**）。

看一个混合体：

```c
struct Mixed { char c; int i; double d; };
```

clang 生成：

```llvm
%struct.Mixed = type { i8, i32, double }
```

注意 `char` 变成了 `i8`，`int` 是 `i32`，`double` 是 `double`。**IR 里没有 `char`/`short`/`int`/`long` 这些名字** —— 只有 `iN`。第 9 章会讲这个映射。

## 6.6 动手练习

**练习 6.1** 生成 `int get_elem(int *a, int i)` 的 `-O2` IR。实测结果是：

```llvm
define dso_local i32 @get_elem(ptr nocapture noundef readonly %0, i32 noundef %1) local_unnamed_addr #0 {
  %3 = sext i32 %1 to i64
  %4 = getelementptr inbounds i32, ptr %0, i64 %3
  %5 = load i32, ptr %4, align 4, !tbaa !5
  ret i32 %5
}
```

**`sext` 还在。** 为什么优化器不干脆用 `i32` 索引？因为 `getelementptr` 的索引语义是「按元素移动」，而地址运算在 64 位平台上必须用 64 位整数完成 —— 索引宽度决定了**计算地址时的回绕行为**。用 `i32` 索引意味着「先按 32 位算出偏移，再扩到 64 位」，这在指针接近地址空间边界时结果不同，而且**负索引**的处理也不一样。LLVM 保留 64 位索引以保证语义精确。

（`nocapture` 表示这个指针不会被存到别处；`readonly` 表示不通过它写内存。这些都是 clang 的推断结果。）

**练习 6.2** 手写一个 `.ll`，定义 `%struct.Pair = type { i64, i64 }`，写一个函数 `@get_second(ptr %p) -> i64` 返回第二个字段。用 `llvm-as-18` 验证，并写 C 驱动测试。

**练习 6.3** 解释下面两者的区别，并各写一个用例：
```llvm
%a = getelementptr inbounds %struct.Point, ptr %p, i32 0, i32 1
%b = getelementptr inbounds %struct.Point, ptr %p, i64 1, i32 1
```

**练习 6.4** 写一个函数 `int *advance(int *p, int n)`，返回 `p + n`。手写 IR，注意索引的类型转换。

**练习 6.5（思考题）** 为什么 LLVM 要设计 `getelementptr` 这样一条「只算地址不访问内存」的指令，而不是让 `load`/`store` 直接带索引？提示：想想公共子表达式消除（CSE）和「地址」作为一等值。

**练习 6.6** 编译 `static int hidden = 1; int pub = 2;` 并观察 `internal` 与默认链接属性的差别。用 `nm` 或 `llvm-nm-18` 检查符号可见性。

## 6.7 小结

- 全局变量用 `@`，`global` 可写、`constant` 只读，`internal` 等价于 C 的 `static`，`external` 等价于 `extern`。
- `alloca` 在栈上分配，随函数返回自动释放；IR 里没有 `free`。
- **`getelementptr` 只算地址，不访问内存。** 读用 `load`，写用 `store`。
- GEP 的索引是**元素个数**，不是字节数；`sizeof` 由 GEP 自动处理。
- 结构体需要**两个**索引：第一个是数组步长（通常 0），第二个是字段号。
- `inbounds` 是「不越界」的承诺，代价是越界即 UB，收益是更多优化。
- `sext` + `getelementptr` 是 32 位索引访问 64 位地址空间的常见模式。

下一章我们看函数与调用。

---

<!-- nav -->
[目录](00-前言.md) · [← 上一章：第 5 章 控制流：`br`、基本块与 `phi`](05-第5章-控制流与phi.md) · [下一章：第 7 章 函数、调用约定与链接 →](07-第7章-函数与调用.md)
