# 第 2 章 你的第一个 IR：`mul_add` 的三行真相

## 2.1 从最小的函数开始

这是本书的第一个 C 函数，也是全书的锚点：

```c
int mul_add(int x, int y, int z) {
    return x * y + z;
}
```

先把源码存成 `mul_add.c`。现在，请打开终端，亲手运行：

```bash
clang-18 -S -emit-llvm -O0 mul_add.c -o -
```

你会看到（我省略了 `; ModuleID`、`source_filename`、`!llvm.ident` 这几行与教学无关的内容）：

```llvm
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"

; Function Attrs: noinline nounwind optnone uwtable
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
  store i32 %0, ptr %4, align 4
  store i32 %1, ptr %5, align 4
  store i32 %2, ptr %6, align 4
  %7 = load i32, ptr %4, align 4
  %8 = load i32, ptr %5, align 4
  %9 = mul nsw i32 %7, %8
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
  ret i32 %11
}

attributes #0 = { noinline nounwind optnone uwtable "frame-pointer"="all" "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
```

## 2.2 先把「三行」这件事说清楚

很多 LLVM IR 教程——包括本书简介里最初的说法——都会告诉你，`mul_add` 会变成 **`mul`、`add`、`ret` 三行**。

**在 `-O0` 下，这不成立。**

上面这段 IR **函数体里有 12 条指令**（3 条 `alloca`、3 条 `store`、3 条 `load`、1 条 `mul`、1 条 `add`、1 条 `ret`），不是 3 条。如果你照着老教程写代码，然后发现自己的输出跟书上完全不一样，很容易怀疑自己哪里做错了。你没有做错，是那个说法省略了前提。

真相是这样的：**「三行」描述的是优化后的 IR**。让我用 `-O2` 再跑一次：

```bash
clang-18 -S -emit-llvm -O2 mul_add.c -o -
```

```llvm
; Function Attrs: mustprogress nofree norecurse nosync nounwind willreturn memory(none) uwtable
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) local_unnamed_addr #0 {
  %4 = mul nsw i32 %1, %0
  %5 = add nsw i32 %4, %2
  ret i32 %5
}
```

现在它确实是三行了（`mul`、`add`、`ret`）。而且请注意两个有趣的细节：

1. 乘法是 `mul nsw i32 %1, %0` —— **操作数顺序反了**。乘法满足交换律，clang 顺手把 `%0` 放到了第二位（这通常是因为 x86 的 `imul` 指令有编码上的偏好，但这一步发生在 IR 层面）。
2. 参数名从 `%0`、`%1`、`%2` 开始，而优化后的指令编号从 `%4` 开始 —— 因为 `%0..%2` 已被参数占用，函数级计数从 3 之后继续。

**所以本章要教你两件事**，它们同等重要：

- `-O0` 的 IR 长什么样，以及那些 `alloca`/`store`/`load` **为什么不是废物**；
- 优化的 IR 长什么样，以及 `alloca` 是怎么消失的。

## 2.3 逐行拆解 `-O0` 版本

### 函数头

```llvm
define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0 {
```

从左到右：

| 片段 | 含义 |
|---|---|
| `define` | 「这是个函数**定义**」（有函数体）。如果是只有声明没有体，用 `declare`。 |
| `dso_local` | 链接属性：这个符号在当前「动态共享对象」内部解析即可，不必走 GOT/PLT。可以粗略理解为「模块内可见」。 |
| `i32` | **返回类型**。C 的 `int` 在 x86-64 Linux 上正好是 32 位。 |
| `@mul_add` | 函数名。`@` 前缀表示**全局标识符**（函数、全局变量）。局部变量用 `%`。 |
| `(i32 noundef %0, ...)` | 参数列表。每个参数都是「类型 + 属性 + 名字」的形式。 |
| `noundef` | 参数属性：调用者保证不传 `undef`/`poison`。这是 C 语义的产物 —— C 里传未初始化的值是 UB。 |
| `%0`、`%1`、`%2` | 参数名。在 `-O0` 下 clang 不保留原始参数名。 |
| `#0` | 指向下方的属性组 `attributes #0 = {...}`。 |

关于 `%0` 的编号，有个必须知道的规则：**参数先占用从 0 开始的编号，指令随后接着编号**。

三个参数占了 `%0`、`%1`、`%2`，那么第一条指令应该叫 `%3` 才对——但实际是 `%4`。这个「跳号」不是笔误，而是 LLVM 隐式编号规则的一部分。我们来实测一下，先看只有一个参数的函数：

```c
int one(int a) { return a + 1; }
```

```llvm
define dso_local i32 @one(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  ...
```

一个参数只占了 `%0`，可第一条指令是 `%2`，跳过了 `%1`。再看两个参数的：

```c
int two(int a, int b) { return a + b; }
```

```llvm
define dso_local i32 @two(i32 noundef %0, i32 noundef %1) #0 {
  %3 = alloca i32, align 4
  %4 = alloca i32, align 4
  ...
```

两个参数占了 `%0`、`%1`，第一条指令是 `%3`——这次**没有**跳号。

规律藏在这里：**基本块标签和「产生值的指令」共用同一个编号计数器，而不产生值的指令不占号。**

在 `two` 里，两个参数占了 `%0`、`%1`，紧接着匿名入口基本块占了 `%2`，所以第一条 `alloca` 是 `%3`。

在 `one` 里，参数占了 `%0`，入口块占 `%1`，所以第一条 `alloca` 是 `%2`——这就是那个「跳号」的真相。

`mul_add` 同理：三个参数占 `%0`~`%2`，入口块占 `%3`，第一条 `alloca` 是 `%4`。

再看看有分支的函数，证据更直白：

```c
int withbranch(int a) {
    if (a > 0) return 1;
    return 2;
}
```

```llvm
define dso_local i32 @withbranch(i32 noundef %0) #0 {
  %2 = alloca i32, align 4
  %3 = alloca i32, align 4
  store i32 %0, ptr %3, align 4
  %4 = load i32, ptr %3, align 4
  %5 = icmp sgt i32 %4, 0
  br i1 %5, label %6, label %7

6:                                                ; preds = %1
  store i32 1, ptr %2, align 4
  br label %8
  ...
```

`label %6`、`%7`、`%8` 全是**基本块**，不是值。而注释 `; preds = %1` 泄露了入口块的名字就是 `%1`。

这些细节不必记。本章真正要你记住的是实操结论：**不要手写编号，让 LLVM 自己编号；如果你的编译器必须自己编号，那就给每个值起名字（`%t1`、`%a`），避开整套隐式计数规则。** 第 8 章会重新审视这条规则，第 17 章我们写编译器时会看到它如何真实地咬人一口。

### 三条 `alloca`

```llvm
  %4 = alloca i32, align 4
  %5 = alloca i32, align 4
  %6 = alloca i32, align 4
```

`alloca` 在**当前函数的栈帧上**分配一块空间，返回指向它的指针。

- `alloca i32` —— 分配一个 `i32` 大小的空间。
- `align 4` —— 这块内存按 4 字节对齐。
- 返回类型是 `ptr`（LLVM 18 的统一指针类型）。

三条 `alloca` 对应三个参数 `x`、`y`、`z`。**为什么要把参数再复制一份到栈上？** 参数本来就在寄存器里啊。

答案是**调试体验**。在 `-O0` 下，编译器承诺：你在 gdb 里 `print x` 时，永远能看到正确的值。如果 `x` 一直待在寄存器里，而那个寄存器又被后续代码复用了，调试器就看不到它了。把参数存进内存，可以保证它在整个函数生命周期内都有一个稳定的地址。

这就是为什么 `-O0` 的 IR 里到处都是 `alloca`/`store`/`load`：**它是在为调试器服务，不是在为 CPU 服务**。

### 三条 `store`

```llvm
  store i32 %0, ptr %4, align 4
  store i32 %1, ptr %5, align 4
  store i32 %2, ptr %6, align 4
```

把参数的值写进刚才分配的槽位。`store` 的语法是：

```
store <类型> <值>, ptr <目标地址>, align <对齐>
```

注意这里有个 LLVM 18 的特征：目标地址写的是 `ptr`，**不是** `i32*`。在老版本 LLVM（≤14）里你会看到 `store i32 %0, i32* %4, align 4`。LLVM 18 用 opaque pointer，所有指针都是 `ptr`，类型信息由 `store` 的第一个操作数（`i32`）提供。

### 两条 `load` 和 `mul`

```llvm
  %7 = load i32, ptr %4, align 4
  %8 = load i32, ptr %5, align 4
  %9 = mul nsw i32 %7, %8
```

`load` 从内存读出一个 `i32`。`mul` 把它们相乘。

**`nsw` 是什么？** 它是 `No Signed Wrap`（无有符号回绕）。这个关键字的意思是：**如果这次乘法有符号溢出了，结果是 `poison`（毒值），而不是回绕后的值**。

这是 C 语义的直接映射。C 标准规定有符号整数溢出是**未定义行为**。既然程序员保证不会溢出，编译器就可以大胆假设不溢出，并把这个假设写进 IR。如果实际溢出了，程序的行为就是未定义的 —— 编译器没有任何责任。

`nsw` 是后面许多激进的优化能够成立的前提。第 11 章会详细展开。

### `add` 与 `ret`

```llvm
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
  ret i32 %11
```

`ret i32 %11` 返回值并结束函数。

## 2.4 观察：SSA 形式

现在把注意力放在这个事实上：

```llvm
  %7 = load i32, ptr %4, align 4
  %8 = load i32, ptr %5, align 4
  %9 = mul nsw i32 %7, %8
  %10 = load i32, ptr %6, align 4
  %11 = add nsw i32 %9, %10
```

**每一个 `%n` 都只被赋值一次。** 这在 IR 里是硬性规定，叫做 **SSA（Static Single Assignment，静态单赋值）形式**。

在 C 里你可以这样写：

```c
int x = 1;
x = x + 1;   // 同一个变量被赋值两次
x = x * 2;
```

在 IR 里这是**非法的**。你不能写 `%7 = ...` 然后又被赋值成别的。每次赋值产生一个**全新的名字**。

那么问题来了：C 里的可变量，在 IR 里怎么表示？

**答案就是 `alloca` + `store` + `load`。** 内存是可变的，SSA 值不是。变量 `x` 住在 `%4` 这块内存里：

```llvm
  %4 = alloca i32          ; 给 x 分配一块内存
  store i32 1, ptr %4      ; x = 1
  %7 = load i32, ptr %4    ; 读出 x
  %8 = add i32 %7, 1       ; x + 1
  store i32 %8, ptr %4     ; x = x + 1
```

**这就是 `-O0` 下到处都是内存操作的第二个原因** —— 它是最省事的、把可变的 C 变量翻译成不可变的 SSA 形式的办法。

而第 20 章我们会看到，LLVM 的 `mem2reg` pass 可以把这些内存操作**重新变成 SSA 值**，需要的时候还会自动插入 `phi` 节点。换句话说，clang `-O0` 走了一条「先存内存，再优化掉」的路线。

## 2.5 从 `-O0` 到 `-O2`：`alloca` 是怎么消失的

上面已经回答了「为什么 `-O0` 的 IR 这么臃肿」。自然的下一个问题是：**优化后它们去哪了？**

简短回答：一个叫 `mem2reg` 的 pass 会把「从不被取地址的栈槽」提升为 SSA 值，需要时自动插入 `phi`。在我们的例子里，12 条指令会变成 3 条。

完整的实验（含命令、输出，以及为什么你直接跑 `opt` 可能毫无反应）在 [附录 B.1](22-附录B-优化入门.md#b1-alloca-为什么会消失mem2reg) 和 [附录 B.2](22-附录B-优化入门.md#b2-为什么跑-opt-没反应optnone)。

## 2.6 完整对照表

| C 源码 | IR（`-O0`） | IR（`-O2`） |
|---|---|---|
| 函数签名 `int mul_add(int,int,int)` | `define dso_local i32 @mul_add(i32 noundef %0, i32 noundef %1, i32 noundef %2) #0` | `define dso_local i32 @mul_add(...) local_unnamed_addr #0` |
| 参数 `x` 的存储 | `%4 = alloca i32, align 4` + `store i32 %0, ptr %4, align 4` | 消失（参数直接在寄存器中） |
| `x * y` | `%7 = load ...; %8 = load ...; %9 = mul nsw i32 %7, %8` | `%4 = mul nsw i32 %1, %0` |
| `... + z` | `%10 = load ...; %11 = add nsw i32 %9, %10` | `%5 = add nsw i32 %4, %2` |
| `return` | `ret i32 %11` | `ret i32 %5` |
| 指令条数 | 12 | 3 |

## 2.7 动手练习

**练习 2.1** 把 `int` 换成 `long`，重新生成 IR。你预期 `i32` 会变成什么？验证一下。

**练习 2.2** 把函数改成 `float mul_add(float x, float y, float z)`。`mul` 会变成什么？（提示：浮点有专门的指令。）

**练习 2.3** 在函数里加一个「没用」的变量：

```c
int mul_add(int x, int y, int z) {
    int unused = 99;
    return x * y + z;
}
```

`-O0` 和 `-O2` 分别怎么处理 `unused`？

**练习 2.4** 试试 `clang-18 -S -emit-llvm -O1 mul_add.c -o -`，对比 `-O1` 和 `-O2` 的输出是否相同。

**练习 2.5（重要）** 用 `opt-18 -passes=mem2reg` 处理你自己写的某个 C 文件的 `-O0` IR。如果什么都没变，想想是为什么。

## 2.8 小结

- `mul_add` 的函数体在 `-O0` 下是 **12 条指令**，在 `-O2` 下才是 **3 条**。宣称「总是三行」的教程省略了前提。
- `alloca`/`store`/`load` 的存在有两个理由：**服务调试器**，以及**把可变的 C 变量翻译成不可变的 SSA 形式**。
- IR 是 SSA 形式：每个 `%name` 只赋值一次。可变状态必须走内存。
- `nsw` 编码了 C 的「有符号溢出是 UB」这一约定。
- LLVM 18 用 `ptr`，不是 `i32*`。
- `optnone` 会让所有优化 pass 静默失效 —— 这是 `-O0` 的明确要求。

下一章，我们把算术、逻辑和移位的全貌看一遍。

---

<!-- nav -->
[目录](00-前言.md) · [← 上一章：第 1 章 为什么值得学 LLVM IR](01-第1章-为什么学LLVM-IR.md) · [下一章：第 3 章 算术、逻辑与移位 →](03-第3章-算术逻辑移位.md)
