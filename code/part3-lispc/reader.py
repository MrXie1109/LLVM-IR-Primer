"""Reader: turns tokens into s-expressions.

An s-expression is represented with plain Python values:

    integer     ->  Python int
    symbol      ->  Sym instance
    list        ->  Python list

A `Sym` is a distinct type from `str` so that the compiler never confuses
"the symbol foo" with "the string foo".  That distinction matters when we
get to code generation, because a symbol becomes an SSA value reference.
"""

from lexer import LispSyntaxError, tokenize


class Sym:
    """An interned Lisp symbol."""

    __slots__ = ("name",)
    _table = {}

    def __new__(cls, name):
        existing = cls._table.get(name)
        if existing is not None:
            return existing
        self = super().__new__(cls)
        self.name = name
        cls._table[name] = self
        return self

    def __repr__(self):
        return self.name


class Reader:
    def __init__(self, text):
        self.tokens = tokenize(text)
        self.pos = 0

    # -- token helpers -------------------------------------------------
    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    # -- the actual reader ---------------------------------------------
    def read(self):
        """Read exactly one expression and require the input to be exhausted."""
        expr = self.read_expr()
        tok = self.peek()
        if tok.kind != "eof":
            raise LispSyntaxError(
                f"unexpected {tok.value!r} after expression", tok.line, tok.col
            )
        return expr

    def read_expr(self):
        tok = self.next()

        if tok.kind == "int":
            return tok.value

        if tok.kind == "sym":
            return Sym(tok.value)

        if tok.kind == "eof":
            raise LispSyntaxError("unexpected end of input", tok.line, tok.col)

        if tok.value == "(":
            items = []
            while True:
                nxt = self.peek()
                if nxt.kind == "eof":
                    raise LispSyntaxError("unclosed '('", tok.line, tok.col)
                if nxt.kind == "punct" and nxt.value == ")":
                    self.next()
                    return items
                items.append(self.read_expr())

        if tok.value == ")":
            raise LispSyntaxError("unexpected ')'", tok.line, tok.col)

        if tok.value == "'":
            # 'x is sugar for (quote x)
            return [Sym("quote"), self.read_expr()]

        raise LispSyntaxError(f"cannot read {tok.value!r}", tok.line, tok.col)


def read_all(text):
    """Read every top-level form in `text`."""
    reader = Reader(text)
    forms = []
    while reader.peek().kind != "eof":
        forms.append(reader.read_expr())
    return forms


def read_one(text):
    return Reader(text).read()


# -- convenience constructors used by tests and the compiler ----------
def sym(name):
    return Sym(name)


def is_sym(x, name=None):
    if not isinstance(x, Sym):
        return False
    return name is None or x.name == name


def is_list(x):
    return isinstance(x, list)


def unparse(expr):
    """Render an s-expression back to text (used for error messages)."""
    if isinstance(expr, Sym):
        return expr.name
    if isinstance(expr, list):
        return "(" + " ".join(unparse(e) for e in expr) + ")"
    return str(expr)
