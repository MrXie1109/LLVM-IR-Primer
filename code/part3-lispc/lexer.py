"""Lexer for the Tiny Lisp dialect used in this book.

The dialect is deliberately small: integers, symbols, a handful of
punctuation characters, and comments.  Everything about it is chosen so
that the reader can hold the whole grammar in their head and spend their
attention on LLVM IR instead.
"""


class LispSyntaxError(Exception):
    """Raised when the source text cannot be tokenised or parsed."""

    def __init__(self, message, line, col):
        super().__init__(f"line {line}, col {col}: {message}")
        self.message = message
        self.line = line
        self.col = col


# Characters that are tokens all by themselves.
PUNCTUATION = "()'"


class Token:
    __slots__ = ("kind", "value", "line", "col")

    def __init__(self, kind, value, line, col):
        self.kind = kind      # "int" | "sym" | "punct" | "eof"
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r})"


def tokenize(text):
    """Turn source text into a flat list of tokens ending with an EOF token."""
    tokens = []
    i = 0
    line = 1
    col = 1
    n = len(text)

    def advance(k=1):
        # Track line/column so that error messages point at real places.
        nonlocal i, line, col
        for _ in range(k):
            if i < n and text[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        ch = text[i]

        # Whitespace is insignificant.
        if ch in " \t\r\n":
            advance()
            continue

        # Comments run to the end of the line.
        if ch == ";":
            while i < n and text[i] != "\n":
                advance()
            continue

        # Punctuation: one token per character.
        if ch in PUNCTUATION:
            tokens.append(Token("punct", ch, line, col))
            advance()
            continue

        # Integers, optionally signed.  A leading '-' only starts a number
        # if a digit follows, so the symbol '-' stays available.
        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            start_line, start_col = line, col
            start = i
            if ch == "-":
                advance()
            while i < n and text[i].isdigit():
                advance()
            tokens.append(Token("int", int(text[start:i]), start_line, start_col))
            continue

        # Everything else is a symbol.  Symbol characters are anything that
        # is not whitespace, punctuation, a comment starter, or a paren.
        if ch.isalpha() or ch in "_+-*/%=<>!?":
            start_line, start_col = line, col
            start = i
            while i < n and not text[i].isspace() and text[i] not in PUNCTUATION + ";":
                advance()
            tokens.append(Token("sym", text[start:i], start_line, start_col))
            continue

        raise LispSyntaxError(f"unexpected character {ch!r}", line, col)

    tokens.append(Token("eof", None, line, col))
    return tokens
