#!/usr/bin/env python3
"""minimal_codegen.py -- 生成一个 add 函数，仅此而已。"""


class Block:
    """一个基本块：有名字，有指令列表，可以有终结指令。"""

    def __init__(self, label):
        self.label = label
        self.instructions = []
        self.terminator = None

    def add(self, text):
        """在当前块末尾追加一条指令。"""
        if self.terminator is not None:
            raise RuntimeError(
                f"block %{self.label} already terminated; cannot add: {text}"
            )
        self.instructions.append("  " + text)

    def terminate(self, text):
        """设置终结指令。一个块只能有一条。"""
        if self.terminator is not None:
            raise RuntimeError(f"block %{self.label} already has a terminator")
        self.terminator = "  " + text

    def render(self):
        if self.terminator is None:
            raise RuntimeError(f"block %{self.label} has no terminator")
        lines = [f"{self.label}:"] + self.instructions + [self.terminator]
        return "\n".join(lines)


class Function:
    """一个函数：若干个基本块，加上一个「插入点」。"""

    def __init__(self, name, ret_ty, param_types, param_names):
        self.name = name
        self.ret_ty = ret_ty
        self.param_types = param_types
        self.param_names = param_names
        self.blocks = []
        self.current = None          # 插入点
        self.temp = 0

    def new_block(self, label):
        """只创建，不填充。"""
        block = Block(label)
        self.blocks.append(block)
        return block

    def start(self, block):
        """把插入点移到这个块的末尾。"""
        self.current = block
        return block

    def new_temp(self):
        self.temp += 1
        return f"%t{self.temp}"

    def emit(self, text):
        """在当前插入点插入一条指令。"""
        if self.current is None:
            raise RuntimeError(
                "insertion point is not set; call start(new_block(...)) first"
            )
        self.current.add(text)

    def emit_value(self, ty, text):
        """插入一条产生值的指令，返回它的名字。"""
        name = self.new_temp()
        self.emit(f"{name} = {text}")
        return name

    def terminate(self, text):
        """在当前块的末尾设置终结指令。"""
        if self.current is None:
            raise RuntimeError(
                "insertion point is not set; call start(new_block(...)) first"
            )
        self.current.terminate(text)

    def render(self):
        params = ", ".join(
            f"{ty} {n}" for ty, n in zip(self.param_types, self.param_names)
        )
        out = [f"define {self.ret_ty} @{self.name}({params}) {{"]
        for block in self.blocks:
            out.append(block.render())
        out.append("}")
        return "\n".join(out)


def generate_add():
    """生成 define i32 @add(i32 %a, i32 %b)。"""
    fn = Function("add", "i32", ["i32", "i32"], ["%a", "%b"])

    entry = fn.new_block("entry")
    fn.start(entry)

    r = fn.emit_value("i32", "add i32 %a, %b")
    fn.terminate(f"ret i32 {r}")

    return fn.render()


if __name__ == "__main__":
    print(generate_add())
