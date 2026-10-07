"""A small LLVM IR builder, with an optional pure-SSA variable layer.

This module is the heart of the book's Part III.  It knows how to emit
LLVM IR text for a *subset* of the language.

IMPORTANT - what is actually used by our compiler
-------------------------------------------------
`compiler.py` uses this module for the *structural* primitives only:
`Block`, `Function.new_block/start/emit/emit_value/branch/cond_branch/
reserve_block/branch_placeholder/realize/alloca_slot`, and `Module`.

The generic SSA variable machinery further down - `Function.var`,
`set_var`, `seal_block`, `_read_variable`, `_add_phi_operand`,
`_complete_phi`, `materialize_phis` and the `Phi` class - is a complete
implementation of the "sealed block" algorithm (Braun et al., *Simple and
Efficient Construction of Static Single Assignment Form*), but it is
**NOT exercised** by the book's compiler.  Chapter 19.5 proves this with
an instrumentation experiment and explains why we left it in.

The actual strategy of `compiler.py` is a hybrid (see chapter 17.6):

  * function parameters      -> plain SSA values
  * `let` locals (mutable)   -> stack slots (`alloca`), promoted later
                                by LLVM's `mem2reg`
  * the result of an `if`    -> a `phi` emitted by hand in `op_if`,
                                because both branches' predecessors are
                                known by the time we build the merge block

A `while` loop needs no phi at all, because its back edge is not known
while the condition block is being built - which is exactly the problem
the sealed-block algorithm below exists to solve.

The algorithm, for reference:

  * Every local variable lives in exactly one block, its *defining* block.
  * Reading a variable in the block that defines it yields the current
    SSA value directly - no load, no phi.
  * Reading it from a *sealed* block (one whose predecessors are all
    known) yields its value in the nearest dominating block, or a phi at
    the block where the two paths meet.
  * Reading it from an *unsealed* block (one we are still filling in, or
    whose predecessors we do not yet know) records an "incomplete phi"
    that gets patched once the block is sealed.

Given a front end that routes every variable through `var`/`set_var`, the
payoff is that you never have to allocate stack slots and never emit a
`load`/`store` pair just to move a value across a branch.  Our front end
does not take that route.
"""


class IRError(Exception):
    pass


# The LLVM type names we support.  `i1` is how LLVM spells a boolean, and
# the reader should note that there is no `char`, `short`, `long` or `bool`
# here: C's type zoo collapses to "an integer of N bits" plus "a float of
# N bits" in IR.
I32 = "i32"
I64 = "i64"
I1 = "i1"
DOUBLE = "double"

INT_TYPES = {I1, I32, I64}


class Value:
    """An SSA value: either a named local, a constant, or a global."""

    __slots__ = ("ty", "name")

    def __init__(self, ty, name):
        self.ty = ty
        self.name = name

    def __repr__(self):
        return f"Value({self.ty}, {self.name})"


class Phi:
    """A phi node whose incoming list is still being filled in."""

    __slots__ = ("ty", "name", "incoming", "block")

    def __init__(self, ty, name, block):
        self.ty = ty
        self.name = name
        self.incoming = []   # list of (Value, block_label)
        self.block = block


class Block:
    """A basic block under construction."""

    def __init__(self, label):
        self.label = label
        self.instructions = []
        self.terminator = None
        self.sealed = False
        # variable name -> (Value | Phi | None).  `None` means the
        # variable is known not to be defined on every path reaching here.
        self.bindings = {}
        self.predecessors = []
        self.pending = False

    def add(self, text):
        self.instructions.append("  " + text)

    def terminate(self, text):
        if self.terminator is not None:
            raise IRError(f"block %{self.label} already has a terminator")
        self.terminator = "  " + text

    def render(self, prefix=()):
        if self.terminator is None:
            raise IRError(f"block %{self.label} has no terminator")
        body = list(prefix) + self.instructions
        if isinstance(self.terminator, list):
            body = body + self.terminator
        else:
            body = body + [self.terminator]
        return f"{self.label}:\n" + "\n".join(body)


class Function:
    """A function being built: an ordered list of blocks plus bookkeeping."""

    def __init__(self, name, ret_ty, param_types, param_names=None):
        self.name = name
        self.ret_ty = ret_ty
        self.param_types = param_types
        self.param_names = param_names or [f"%a{i}" for i in range(len(param_types))]
        self.blocks = []
        self.block_by_label = {}
        self.temp_counter = 0
        self.label_counter = 0
        self.current = None
        self._reserved = {}
        # Set of variable names whose address has been taken.  Those must
        # live in memory, so `alloca` is used and `var()` degrades to loads.
        self.promoted_blocked = set()
        self.entry_allocas = []

    # -- block management ----------------------------------------------
    def new_block(self, hint="bb"):
        label = self._fresh_label(hint)
        block = Block(label)
        self.blocks.append(block)
        self.block_by_label[label] = block
        return block

    def start(self, block):
        """Begin emitting into `block`, realizing it if it was reserved."""
        if getattr(block, "pending", False):
            block = self.realize(block)
        self.current = block
        return block

    def reserve_block(self, hint="bb"):
        """Reserve a label now, but let the block body be filled in later.

        A forward jump needs a label before the target exists.  Reserving
        the label up front and creating the block at the point where its
        body is actually emitted keeps the printed listing in
        roughly-execution order, which is what a human wants to read.
        """
        label = self._fresh_label(hint)
        placeholder = Block(label)
        placeholder.pending = True
        self._reserved[label] = placeholder
        return placeholder

    def _fresh_label(self, hint):
        label = f"{hint}{self.label_counter}"
        self.label_counter += 1
        while label in self.block_by_label or label in self._reserved:
            label = f"{hint}{self.label_counter}"
            self.label_counter += 1
        return label

    def branch_placeholder(self, placeholder):
        """Terminate the current block with a jump to a reserved block."""
        self.current.terminate(f"br label %{placeholder.label}")
        placeholder.predecessors.append(self.current)

    def realize(self, placeholder):
        """Turn a reserved label into a real, emitted block."""
        block = self.block_by_label.get(placeholder.label)
        if block is not None:
            return block
        block = Block(placeholder.label)
        block.predecessors = placeholder.predecessors
        block.sealed = placeholder.sealed
        self.blocks.append(block)
        self.block_by_label[block.label] = block
        del self._reserved[placeholder.label]
        return block

    def new_temp(self):
        """Allocate a fresh *named* temporary.

        LLVM's textual format has an implicit unnamed counter: an
        instruction whose result is written `%4` must be the fifth
        unnamed value in the function, otherwise the parser rejects the
        file with "instruction expected to be numbered '%N' or greater".
        Keeping our own counter in sync with LLVM's is possible but
        brittle -- for instance, `br i1 %c, label %a, label %b` does not
        consume a slot, but `phi` does.  Naming every temporary sidesteps
        the whole issue, which is why Chapter 8 recommends it.
        """
        self.temp_counter += 1
        return f"%t{self.temp_counter}"

    def emit(self, text):
        self.current.add(text)

    def emit_value(self, ty, text):
        """Emit `text` whose result has type `ty`, returning a Value."""
        name = self.new_temp()
        self.current.add(f"{name} = {text}")
        return Value(ty, name)

    def set_term(self, text):
        self.current.terminate(text)

    def branch(self, target):
        self.current.terminate(f"br label %{target.label}")
        target.predecessors.append(self.current)

    def cond_branch(self, cond, then_block, else_block):
        self.current.terminate(
            f"br i1 {cond.name}, label %{then_block.label}, "
            f"label %{else_block.label}"
        )
        then_block.predecessors.append(self.current)
        else_block.predecessors.append(self.current)

    # -- SSA variable bookkeeping --------------------------------------
    def alloca_slot(self, ty, hint="slot"):
        """Reserve a stack slot in the entry block and return its pointer."""
        name = f"%{hint}.addr"
        # Unique-ify in case the same hint is used twice.
        n = 1
        while any(name in a for a in self.entry_allocas):
            name = f"%{hint}.addr{n}"
            n += 1
        self.entry_allocas.append(f"  {name} = alloca {ty}, align {self._align(ty)}")
        return Value(f"ptr", name)

    @staticmethod
    def _align(ty):
        if ty in (I64, DOUBLE):
            return 8
        if ty == I32:
            return 4
        if ty == I1:
            return 1
        return 8

    def var(self, name, ty):
        """Read variable `name`, materialising a phi if necessary."""
        block = self.current
        if name in self.promoted_blocked:
            return self._load_slot(name, ty)
        val = self._read_variable(name, block)
        if val is None:
            # The variable is not defined on at least one path into here.
            if not block.sealed and any(
                p for p in block.predecessors
            ) is False and not block.predecessors:
                # Entry-ish block with no predecessors: fall back to 0.
                return Value(ty, "0")
            return Value(ty, "0")
        return val

    def set_var(self, name, ty, value):
        if name in self.promoted_blocked:
            self._store_slot(name, ty, value)
            return
        self._write_variable(name, self.current, value)

    def _read_variable(self, name, block):
        if name in block.bindings:
            entry = block.bindings[name]
            if isinstance(entry, Phi):
                return self._add_phi_operand(entry, block)
            return entry

        if not block.sealed:
            # We do not know all predecessors yet, so we cannot decide
            # whether a phi is needed.  Make one provisionally and patch
            # it in `seal_block`.
            phi = Phi(I32, self._reserve_phi_name(block), block)
            block.bindings[name] = phi
            val = self._add_phi_operand(phi, block)
            return val

        if len(block.predecessors) == 0:
            return None
        if len(block.predecessors) == 1:
            val = self._read_variable(name, block.predecessors[0])
            block.bindings[name] = val
            return val

        # More than one predecessor: we need a phi, and we must recurse
        # first so that the operands are correct.
        phi = Phi(I32, self._reserve_phi_name(block), block)
        block.bindings[name] = phi
        return self._add_phi_operand(phi, block)

    def _reserve_phi_name(self, block):
        # Phi names come from the function-wide temp counter, which keeps
        # numbering consistent with LLVM's own convention.
        return self.new_temp()

    def _add_phi_operand(self, phi, block):
        if len(block.predecessors) == 0:
            # Unreachable fill-in: self-reference keeps the IR verifiable.
            phi.incoming.append((Value(phi.ty, "0"), block.label))
            return phi
        if len(phi.incoming) == len(block.predecessors):
            # Already complete: the value defined by the phi itself is the
            # answer inside this block.
            return phi
        pred = block.predecessors[len(phi.incoming)]
        val = self._read_variable_operand(phi, pred)
        phi.incoming.append((val, pred.label))
        return phi

    def _read_variable_operand(self, phi, pred):
        """Read `phi`'s variable as seen at the end of `pred`."""
        # Find the variable name this phi belongs to.
        name = None
        for k, v in phi.block.bindings.items():
            if v is phi:
                name = k
                break
        if name is None:
            raise IRError("phi is not bound to any variable")
        val = self._read_variable(name, pred)
        if val is None:
            return Value(phi.ty, "0")
        return val

    def _write_variable(self, name, block, value):
        if name in block.bindings and isinstance(block.bindings[name], Phi):
            phi = block.bindings[name]
            # A phi already exists here for this name: from inside the
            # block, the phi *is* the variable, so rebinding is a no-op
            # for readers and we simply record the definition.
            pass
        block.bindings[name] = value
        # If this block already handed out a phi, later readers inside the
        # block should see the phi, not the new value; that is exactly
        # what LLVM's own -O0 pipeline must reason about too.

    def seal_block(self, block):
        if block.sealed:
            return
        block.sealed = True
        for name, entry in list(block.bindings.items()):
            if isinstance(entry, Phi):
                self._complete_phi(entry, block)

    def _complete_phi(self, phi, block):
        while len(phi.incoming) < len(block.predecessors):
            pred = block.predecessors[len(phi.incoming)]
            val = self._read_variable_operand(phi, pred)
            phi.incoming.append((val, pred.label))
        if not phi.incoming:
            # Block with no predecessors: drop the phi, bind 0.
            for k, v in list(block.bindings.items()):
                if v is phi:
                    block.bindings[k] = Value(phi.ty, "0")

    def materialize_phis(self):
        """Insert phi instructions at the top of every block that needs them."""
        for block in self.blocks:
            phis = [
                (name, entry)
                for name, entry in block.bindings.items()
                if isinstance(entry, Phi)
            ]
            if not phis:
                continue
            # Deterministic order, and emit only phis that survived.
            lines = []
            for _name, phi in sorted(phis, key=lambda kv: kv[1].name):
                incoming = ", ".join(
                    f"[ {val.name}, %{label} ]" for val, label in phi.incoming
                )
                lines.append(f"  {phi.name} = phi {phi.ty} {incoming}")
            block.instructions = lines + block.instructions

    # -- rendering ------------------------------------------------------
    def render(self):
        self.materialize_phis()
        params = ", ".join(
            f"{ty} {name}" for ty, name in zip(self.param_types, self.param_names)
        )
        header = f"define {self.ret_ty} @{self.name}({params}) {{"
        lines = [header]
        for index, block in enumerate(self.blocks):
            # `alloca` instructions belong at the top of the entry block,
            # *after* its label -- an instruction cannot appear before the
            # first basic block of a function.
            prefix = self.entry_allocas if index == 0 else []
            lines.append(block.render(prefix))
        lines.append("}")
        return "\n".join(lines)


class Module:
    """A whole translation unit: globals, declarations, definitions."""

    def __init__(self, name="lisp_module"):
        self.name = name
        self.globals = []
        self.declarations = []
        self.functions = []

    def add_global(self, ty, name, init, constant=False):
        kw = "constant" if constant else "global"
        self.globals.append(f"@{name} = {kw} {ty} {init}, align 4")

    def declare(self, ret_ty, name, param_types):
        params = ", ".join(param_types)
        self.declarations.append(f"declare {ret_ty} @{name}({params})")

    def add_function(self, fn):
        self.functions.append(fn)

    def render(self, triple=None, datalayout=None):
        parts = []
        if datalayout:
            parts.append(f'target datalayout = "{datalayout}"')
        if triple:
            parts.append(f'target triple = "{triple}"')
        if parts:
            parts.append("")
        parts.extend(self.globals)
        if self.globals:
            parts.append("")
        parts.extend(self.declarations)
        if self.declarations:
            parts.append("")
        for fn in self.functions:
            parts.append(fn.render())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"
