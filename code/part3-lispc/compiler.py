"""Compile the Tiny Lisp dialect to LLVM IR.

Source language (all forms are s-expressions):

    (defn name (params...) body...)     ; function definition
    (defg name init)                    ; global variable
    (let ((v e)...) body...)            ; local bindings
    (if cond then else)                 ; conditional expression
    (while cond body...)                ; loop, yields 0
    (+ a b), (- a b), (* a b), (/ a b)  ; signed arithmetic
    (< a b) (<= ...) (= ...)            ; comparisons yielding i1
    (f args...)                         ; call

Every expression has the type i32 except comparisons, which produce i1.
That restriction is deliberate: it keeps the book focused on IR
generation rather than on a type system.
"""

import sys
from ir import DOUBLE, Function, I1, I32, IRError, Module, Value
from reader import Sym, is_sym, read_all, unparse

# --------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------


class Var:
    """A Lisp variable, either an SSA value or a stack slot.

    Two representations, and the choice between them is one of the most
    instructive decisions in the whole compiler:

    * `slot=True`  -- the variable lives in memory (`alloca`), and reads
      and writes become `load`/`store`.  This is always correct, which is
      why clang -O0 does it for every C local.

    * `slot=False` -- the variable is a pure SSA value.  This is smaller
      and faster, but a variable reassigned inside a loop needs a `phi`
      node, which is genuinely hard to get right in a single pass.

    We take the easy, always-correct road: mutable locals get a slot,
    immutable ones stay in SSA registers.  Then we let LLVM's `mem2reg`
    promotion pass recover the SSA form for us -- and in Chapter 20 we
    read the `phi` nodes it produces.
    """

    __slots__ = ("ir_name", "ty", "slot", "mutable")

    def __init__(self, ir_name, ty, slot, mutable=False):
        self.ir_name = ir_name
        self.ty = ty
        self.slot = slot
        self.mutable = mutable


class Frame:
    """A lexical scope mapping Lisp names to `Var` objects."""

    def __init__(self, parent=None):
        self.parent = parent
        self.vars = {}

    def lookup(self, name):
        frame = self
        while frame is not None:
            if name in frame.vars:
                return frame.vars[name]
            frame = frame.parent
        return None

    def define(self, name, var):
        self.vars[name] = var

    def defined_here(self, name):
        return name in self.vars


class FunctionSig:
    def __init__(self, name, ret_ty, param_types):
        self.name = name
        self.ret_ty = ret_ty
        self.param_types = param_types


# Every user function is emitted with this prefix.  Lisp happily allows a
# function called `double` or `abs`; C's standard headers already own
# those identifiers.  Mangling the emitted symbol keeps generated modules
# linkable with ordinary C code without collisions.
SYMBOL_PREFIX = "l_"


def mangle(name):
    return SYMBOL_PREFIX + name


# Lisp operator symbol -> Python method suffix.  Keeping this table
# explicit (rather than mangling the symbol mechanically) matters because
# several Lisp spellings -- `<`, `=`, `/` -- are not legal Python
# identifier characters.
OPERATOR_METHODS = {
    "let": "op_let",
    "if": "op_if",
    "while": "op_while",
    "set": "op_set",
    "+": "op_add",
    "-": "op_sub",
    "*": "op_mul",
    "/": "op_div",
    "%": "op_mod",
    "<": "op_lt",
    "<=": "op_le",
    ">": "op_gt",
    ">=": "op_ge",
    "=": "op_eq",
    "==": "op_eq",
    "!=": "op_ne",
}


# --------------------------------------------------------------------
# Compiler
# --------------------------------------------------------------------


class Compiler:
    def __init__(self):
        self.module = Module()
        self.sigs = {}
        # User-defined globals: name -> (ir name, type)
        self.globals = {}

    # -- top level ------------------------------------------------------
    def compile_program(self, text):
        forms = read_all(text)
        # Pass 1: collect signatures and globals so that forward
        # references (in particular recursion) work.
        for form in forms:
            self.collect(form)
        # Pass 2: emit bodies.
        for form in forms:
            self.emit_top(form)
        return self.module

    def collect(self, form):
        if not isinstance(form, list) or not form:
            raise IRError(f"top-level form must be a list: {unparse(form)}")
        head = form[0]
        if is_sym(head, "defn"):
            self._check_defn_shape(form)
            name = form[1].name
            params = [p.name for p in form[2]]
            self.sigs[name] = FunctionSig(mangle(name), I32, [I32] * len(params))
        elif is_sym(head, "defg"):
            self._check_defg_shape(form)
            self.globals[form[1].name] = (f"@{form[1].name}", I32)
        elif is_sym(head, "declare"):
            self._check_declare_shape(form)
            name = form[1].name
            nparams = len(form[2])
            self.sigs[name] = FunctionSig(mangle(name), I32, [I32] * nparams)
        else:
            raise IRError(
                f"unknown top-level form {unparse(head)}; "
                "expected defn, defg or declare"
            )

    @staticmethod
    def _check_defn_shape(form):
        if len(form) < 4:
            raise IRError("defn needs a name, a parameter list and a body")
        if not isinstance(form[1], Sym):
            raise IRError("defn name must be a symbol")
        if not isinstance(form[2], list):
            raise IRError("defn parameter list must be a list")
        for p in form[2]:
            if not isinstance(p, Sym):
                raise IRError(f"parameter must be a symbol, got {unparse(p)}")

    @staticmethod
    def _check_defg_shape(form):
        if len(form) != 3:
            raise IRError("defg needs a name and an initialiser")

    @staticmethod
    def _check_declare_shape(form):
        if len(form) != 3 or not isinstance(form[2], list):
            raise IRError("declare needs a name and a parameter type list")

    def emit_top(self, form):
        head = form[0]
        if is_sym(head, "defn"):
            self.module.add_function(self.compile_function(form))
        elif is_sym(head, "defg"):
            _, name, init = form
            if not isinstance(init, int):
                raise IRError("global initialiser must be an integer constant")
            self.module.add_global(I32, name.name, init)
        elif is_sym(head, "declare"):
            _, name, _params = form
            sig = self.sigs[name.name]
            self.module.declare(sig.ret_ty, sig.name, sig.param_types)

    # -- functions ------------------------------------------------------
    def compile_function(self, form):
        _, name, params, *body = form
        param_names = [p.name for p in params]
        sig = self.sigs[name.name]
        fn = Function(
            sig.name,
            sig.ret_ty,
            sig.param_types,
            [f"%{p}" for p in param_names],
        )

        entry = fn.new_block("entry")
        fn.start(entry)

        env = Frame()
        for lisp_name, ir_name in zip(param_names, fn.param_names):
            env.define(lisp_name, Var(ir_name, I32, slot=False))

        # A body is an implicit (do ...): evaluate each form, return the last.
        result = Value(I32, "0")
        for expr in body:
            result = self.compile_expr(fn, env, expr)
        fn.set_term(f"ret i32 {result.name}")
        fn.seal_block(entry)
        return fn

    # -- expressions ----------------------------------------------------
    def compile_expr(self, fn, env, expr):
        if isinstance(expr, int):
            return Value(I32, str(expr))

        if isinstance(expr, Sym):
            var = env.lookup(expr.name)
            if var is not None:
                return self.read_var(fn, var)
            if expr.name in self.globals:
                ir_name, ty = self.globals[expr.name]
                return fn.emit_value(ty, f"load {ty}, ptr {ir_name}, align 4")
            raise IRError(f"unbound variable {expr.name!r}")

        if not isinstance(expr, list) or not expr:
            raise IRError(f"cannot compile {unparse(expr)}")

        head = expr[0]
        if not isinstance(head, Sym):
            raise IRError(f"head of {unparse(expr)} must be a symbol")

        handler_name = OPERATOR_METHODS.get(head.name)
        handler = getattr(self, handler_name, None) if handler_name else None
        if handler is None:
            if head.name in self.sigs:
                return self.compile_call(fn, env, expr)
            raise IRError(f"unknown operator or function {head.name!r}")
        return handler(fn, env, expr)

    # -- variable access ------------------------------------------------
    def read_var(self, fn, var):
        """Turn a `Var` into an SSA `Value` at the current program point."""
        if var.slot:
            # Reading a slot is a `load`; the type is carried by the slot.
            return fn.emit_value(
                var.ty, f"load {var.ty}, ptr {var.ir_name}, align 4"
            )
        return Value(var.ty, var.ir_name)

    # -- special forms --------------------------------------------------
    def op_let(self, fn, env, expr):
        """(let ((v e) ...) body...) -- introduce locals.

        Every binding is stored in a stack slot rather than an SSA
        register, because `let` bindings are mutable in this dialect (see
        `set`).  Chapter 20 shows how `mem2reg` turns them back into
        registers.
        """
        if len(expr) < 3:
            raise IRError("let needs a binding list and a body")
        _, bindings, *body = expr
        if not isinstance(bindings, list):
            raise IRError("let bindings must be a list of pairs")

        inner = Frame(env)
        for pair in bindings:
            if not isinstance(pair, list) or len(pair) != 2:
                raise IRError(f"bad let binding {unparse(pair)}")
            name = pair[0]
            if not isinstance(name, Sym):
                raise IRError("let binding name must be a symbol")
            val = self.compile_expr(fn, inner, pair[1])
            slot = fn.alloca_slot(I32, hint=f"{name.name}")
            fn.emit(f"store i32 {val.name}, ptr {slot.name}, align 4")
            inner.define(name.name, Var(slot.name, I32, slot=True, mutable=True))

        result = Value(I32, "0")
        for form in body:
            result = self.compile_expr(fn, inner, form)
        return result

    def op_set(self, fn, env, expr):
        """(set v e) -- assign to an existing local."""
        if len(expr) != 3:
            raise IRError("set takes a variable and a value")
        _, target, value_expr = expr
        if not isinstance(target, Sym):
            raise IRError("set target must be a symbol")
        var = env.lookup(target.name)
        if var is None:
            raise IRError(f"set of unbound variable {target.name!r}")
        if not var.slot:
            raise IRError(
                f"cannot assign to {target.name!r}: it is an SSA value, "
                "not a local slot"
            )
        val = self.compile_expr(fn, env, value_expr)
        fn.emit(f"store i32 {val.name}, ptr {var.ir_name}, align 4")
        return val

    def op_if(self, fn, env, expr):
        """(if c t e) -- conditional expression, yielding a value."""
        if len(expr) != 4:
            raise IRError("if takes exactly a condition, a then and an else")
        _, cond_expr, then_expr, else_expr = expr
        cond = self.to_i1(fn, self.compile_expr(fn, env, cond_expr))

        # Allocate then/else up front, but the merge block *after* the
        # arms are compiled.  This matters: a nested `if` in the else arm
        # allocates its own blocks while we are building, and if the merge
        # block had already been reserved it would be emitted before the
        # nested blocks that branch into it.  LLVM accepts any block
        # order, but printing a block before its predecessors makes the
        # listing far harder to read -- and `phi` operands must refer to
        # blocks, not to positions, so ordering is purely cosmetic.
        then_block = fn.new_block("then")
        else_block = fn.new_block("else")
        merge_ref = fn.reserve_block("merge")

        fn.cond_branch(cond, then_block, else_block)

        # Compile the then arm.  Note that we compile the expression
        # *before* emitting the jump to the merge block: a nested `if`
        # inside the arm leaves the builder sitting in its own merge
        # block, and that block -- not `then_block` -- is the arm's real
        # predecessor of the merge point.
        fn.start(then_block)
        then_val = self.compile_expr(fn, env, then_expr)
        then_end = fn.current
        fn.branch_placeholder(merge_ref)

        fn.start(else_block)
        else_val = self.compile_expr(fn, env, else_expr)
        else_end = fn.current
        fn.branch_placeholder(merge_ref)

        # The merge point has exactly two predecessors, so the result of
        # the `if` is a two-input phi -- the single most important pattern
        # in all of LLVM IR.
        fn.start(merge_ref)
        if then_val.name == else_val.name:
            return then_val
        return fn.emit_value(
            then_val.ty,
            f"phi {then_val.ty} [ {then_val.name}, %{then_end.label} ], "
            f"[ {else_val.name}, %{else_end.label} ]",
        )

    def op_while(self, fn, env, expr):
        """(while c body...) -- loop; yields 0.

        Because every mutable local lives in a slot, the loop needs no
        phi nodes at all: the slot is the phi.  This is precisely the
        trade-off clang -O0 makes, and it is why -O0 output is so full of
        loads and stores.
        """
        if len(expr) < 2:
            raise IRError("while needs a condition")
        _, cond_expr, *body = expr
        cond_block = fn.new_block("while.cond")
        body_block = fn.new_block("while.body")
        end_block = fn.new_block("while.end")

        fn.branch(cond_block)

        fn.start(cond_block)
        cond = self.to_i1(fn, self.compile_expr(fn, env, cond_expr))
        fn.cond_branch(cond, body_block, end_block)

        fn.start(body_block)
        for form in body:
            self.compile_expr(fn, env, form)
        fn.branch(cond_block)

        fn.seal_block(cond_block)
        fn.start(end_block)
        return Value(I32, "0")

    # -- calls ----------------------------------------------------------
    def compile_call(self, fn, env, expr):
        head = expr[0].name
        sig = self.sigs[head]
        args = [self.compile_expr(fn, env, a) for a in expr[1:]]
        if len(args) != len(sig.param_types):
            raise IRError(
                f"{head} expects {len(sig.param_types)} arguments, "
                f"got {len(args)}"
            )
        arg_text = ", ".join(
            f"{ty} {a.name}" for ty, a in zip(sig.param_types, args)
        )
        return fn.emit_value(
            sig.ret_ty, f"call {sig.ret_ty} @{sig.name}({arg_text})"
        )

    # -- arithmetic -----------------------------------------------------
    def _binary(self, fn, env, expr, opname, ret_ty=I32):
        _, a, b = expr
        va = self.compile_expr(fn, env, a)
        vb = self.compile_expr(fn, env, b)
        return fn.emit_value(ret_ty, f"{opname} {va.ty} {va.name}, {vb.name}")

    def op_add(self, fn, env, expr):
        return self._binary(fn, env, expr, "add")

    def op_sub(self, fn, env, expr):
        return self._binary(fn, env, expr, "sub")

    def op_mul(self, fn, env, expr):
        return self._binary(fn, env, expr, "mul")

    def op_div(self, fn, env, expr):
        return self._binary(fn, env, expr, "sdiv")

    def op_mod(self, fn, env, expr):
        return self._binary(fn, env, expr, "srem")

    def op_lt(self, fn, env, expr):
        return self._binary(fn, env, expr, "icmp slt", ret_ty=I1)

    def op_le(self, fn, env, expr):
        return self._binary(fn, env, expr, "icmp sle", ret_ty=I1)

    def op_gt(self, fn, env, expr):
        return self._binary(fn, env, expr, "icmp sgt", ret_ty=I1)

    def op_ge(self, fn, env, expr):
        return self._binary(fn, env, expr, "icmp sge", ret_ty=I1)

    def op_eq(self, fn, env, expr):
        return self._binary(fn, env, expr, "icmp eq", ret_ty=I1)

    def op_ne(self, fn, env, expr):
        return self._binary(fn, env, expr, "icmp ne", ret_ty=I1)

    def to_i1(self, fn, val):
        """Coerce an i32 into an i1, which is what `br` demands."""
        if val.ty == I1:
            return val
        return fn.emit_value(I1, f"icmp ne {val.ty} {val.name}, 0")


# --------------------------------------------------------------------


def compile_text(text):
    return Compiler().compile_program(text)


def main(argv):
    if len(argv) != 2:
        print("usage: python3 compiler.py FILE.lisp", file=sys.stderr)
        return 2
    with open(argv[1], "r") as fh:
        src = fh.read()
    try:
        module = compile_text(src)
    except (IRError, Exception) as exc:  # noqa: BLE001 - report cleanly
        print(f"compile error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(module.render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
