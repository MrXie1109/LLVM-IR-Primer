# Chapter 16 Lexing and Parsing

## 16.1 Referring Back: The "Symbol vs. Integer" Distinction from Chapter 8

Chapter 8 explained the two forms of identifier: named values `%name` and numbered values `%0`. One point was emphasised there:

> **A named value cannot begin with a digit, otherwise it will be parsed as a numbered value.**

This pitfall has an exactly corresponding version in **our own language**. Look at these two expressions:

```lisp
(+ x 1)
(+ x -1)
```

The first `1` is an integer. What about the second, `-1`? It could be:
- the integer "minus one";
- or the symbol `-` followed by the integer `1` (that is, `(- 1)`, a subtraction).

**This ambiguity must be resolved already at the lexing stage.** Our rule is:

> **When `-` is immediately followed by a digit, it is a negative integer; otherwise it is the subtraction symbol.**

This is the same kind of problem as LLVM's `%1abc` in Chapter 8: **the splitting rules at the lexical level determine the structure at the syntactic level**. This chapter writes that splitter.

## 16.2 Overall Architecture: Two Passes

```
source text
   │
   │  ① lexer.py: characters -> tokens
   ▼
token stream: [Token(punct,"("), Token(sym,"+"), Token(int,1), ...]
   │
   │  ② reader.py: tokens -> S-expressions
   ▼
S-expressions: [Sym(+), 1, 2]
   │
   │  ③ compiler.py (Chapters 17–19)
   ▼
LLVM IR
```

**Why two passes?** Because the judgements the two passes make are **different in nature**:

- Lexing only cares about **local character patterns** ("these few characters are a number");
- Parsing cares about **nested structure** ("which `(` does this `)` match").

Writing them together (building the tree while scanning) is feasible, but it makes error reporting harder, and it leaves judgements such as "distinguish symbols from integers" with nowhere to live. Once they are separated, each pass can be tested on its own.

## 16.3 Lexing: `lexer.py`

### Representing a Token

```python
class Token:
    __slots__ = ("kind", "value", "line", "col")

    def __init__(self, kind, value, line, col):
        self.kind = kind      # "int" | "sym" | "punct" | "eof"
        self.value = value
        self.line = line
        self.col = col
```

There are only four kinds of token:

| `kind` | `value` | Examples |
|---|---|---|
| `"int"` | a Python `int` | `42`, `-7` |
| `"sym"` | a string | `defn`, `+`, `fib` |
| `"punct"` | `"("`, `")"`, `"'"` | `(` |
| `"eof"` | `None` | end-of-input marker |

**Why record `line` and `col`?** Because an error message must be able to point at the exact position in the source. This is the first appearance of "user experience" inside a compiler:

```
line 3, col 12: unclosed '('
```

That is a hundred times more useful than `SyntaxError: something went wrong`.

### The Main Loop

```python
def tokenize(text):
    tokens = []
    i = 0
    line = 1
    col = 1
    n = len(text)

    def advance(k=1):
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

        if ch in " \t\r\n":          # whitespace: skip
            advance()
            continue

        if ch == ";":                # comment: skip to end of line
            while i < n and text[i] != "\n":
                advance()
            continue

        if ch in PUNCTUATION:        # parentheses and quote: one-character token
            tokens.append(Token("punct", ch, line, col))
            advance()
            continue

        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            # integer (possibly negative)
            ...

        if ch.isalpha() or ch in "_+-*/%=<>!?":
            # symbol
            ...

        raise LispSyntaxError(f"unexpected character {ch!r}", line, col)

    tokens.append(Token("eof", None, line, col))
    return tokens
```

### Key Point One: The Rule for Recognising Negative Numbers

This is the handling of the ambiguity from the start of the chapter:

```python
if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
    start = i
    if ch == "-":
        advance()                    # consume the minus sign
    while i < n and text[i].isdigit():
        advance()
    tokens.append(Token("int", int(text[start:i]), start_line, start_col))
```

**The core condition**: `ch == "-" and the next character is a digit`.

- `-1` → the minus sign is followed by `1`, so it is recognised as the integer `-1`;
- `-` on its own → the next character is not a digit, so it falls through to the symbol branch and is recognised as the symbol `-`;
- `a-1` → at `a` the whole of `a-1` has already been consumed as a symbol (see the next section).

Measured:

```python
>>> from reader import read_one, unparse
>>> unparse(read_one('(- 5 3)'))
'(- 5 3)'                      # '-' is a symbol, 5 and 3 are integers
>>> read_one('-7')
-7                             # negative integer
```

### Key Point Two: The Symbol Character Set

```python
if ch.isalpha() or ch in "_+-*/%=<>!?":
    start = i
    while i < n and not text[i].isspace() and text[i] not in PUNCTUATION + ";":
        advance()
    tokens.append(Token("sym", text[start:i], start_line, start_col))
```

The **starting character** must be a letter or one of `_+-*/%=<>!?`. This prevents symbols that "begin with a digit" (the lesson of Chapter 8).

The **subsequent characters** are far more permissive: anything that is not whitespace, a parenthesis or a semicolon will do. So `sum_to`, `<=` and `!=` are all recognised correctly.

**Note that `-` is also a legal symbol starting character.** This is necessary, because the `-` in `(- a b)` has to be recognised as a symbol. The negative-number rule above handles the case "`-` followed by a digit" first, and only the remaining `-` characters reach the symbol branch.

### Key Point Three: Comments

```python
if ch == ";":
    while i < n and text[i] != "\n":
        advance()
    continue
```

Comments are skipped directly and produce no token. **Note that a comment ends at a newline**, not at some terminator character.

### Error Reporting

```python
raise LispSyntaxError(f"unexpected character {ch!r}", line, col)
```

`LispSyntaxError` formats the position information into a readable message:

```python
class LispSyntaxError(Exception):
    def __init__(self, message, line, col):
        super().__init__(f"line {line}, col {col}: {message}")
        self.message = message
        self.line = line
        self.col = col
```

Measured:

```python
>>> from reader import read_one
>>> read_one('(foo bar')
LispSyntaxError: line 1, col 1: unclosed '('
>>> read_one(')')
LispSyntaxError: line 1, col 1: unexpected ')'
```

## 16.4 Parsing: `reader.py`

### The In-Memory Representation of S-Expressions

We represent S-expressions with **ordinary Python values**:

```
Lisp form      Python representation
42        →    int 42
foo       →    Sym("foo")
(+ 1 2)   →    [Sym("+"), 1, 2]
(quote x) →    [Sym("quote"), Sym("x")]
```

**Why not use custom AST node classes?** Because an S-expression is itself a nested list, and representing it with a Python `list` is **zero impedance**. This follows the same reasoning as "we chose Lisp because its syntax is simple" — do not introduce unnecessary abstraction.

**But symbols must use a dedicated type** (`Sym`) rather than `str`. The reason:

```python
"foo" == "foo"      # strings compare their contents
Sym("foo") == Sym("foo")   # this also has to compare identity
```

If symbols were `str`, the code could not tell "the symbol `foo`" apart from "the string constant `"foo"`". **Our language has no string constants, but the code generator contains a lot of strings (IR text, error messages), and this distinction matters.**

`Sym` is implemented with **interning**, so symbols with the same name are the same object and can be compared with `is`:

```python
class Sym:
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
```

Measured:

```python
>>> from reader import Sym
>>> Sym("foo") is Sym("foo")
True
```

### Recursive-Descent Reading

```python
class Reader:
    def __init__(self, text):
        self.tokens = tokenize(text)
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def read(self):
        """Read exactly one expression, and require the input to be exhausted."""
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
            return [Sym("quote"), self.read_expr()]

        raise LispSyntaxError(f"cannot read {tok.value!r}", tok.line, tok.col)
```

**That is the entire parser.** It is only 40 lines, because the syntax of S-expressions is just "nested parentheses" — no operator precedence, no ambiguity, and no backtracking.

Compare that: to parse C's `a + b * c` you need a precedence table or a layered grammar. In Lisp, the nesting of `(+ a (* b c))` **already** expresses the precedence.

### Handling Errors: Why `unclosed '('` Points at the Beginning

Note this line:

```python
raise LispSyntaxError("unclosed '('", tok.line, tok.col)
```

It reports the position of **the unclosed left parenthesis** (`tok` is the `(` that was first read), not the position of the end of the file.

This is deliberate: **when parentheses do not match, the user wants to know "which parenthesis started it", not "where the file ends".**

Measured:

```python
>>> read_one('(foo bar')
LispSyntaxError: line 1, col 1: unclosed '('
```

It points at col 1, that is, at that `(`. If it pointed at the end of the file, the user would have to search backwards themselves.

### The Top-Level Interface

```python
def read_all(text):
    """Read every top-level expression in the text."""
    reader = Reader(text)
    forms = []
    while reader.peek().kind != "eof":
        forms.append(reader.read_expr())
    return forms
```

`read_all` is used for the case where a single file contains several `defn`s.

## 16.5 A Complete Round-Trip Test

Let us verify the whole front end:

```python
>>> from reader import read_all, read_one, unparse
>>> unparse(read_one('(+ 1 2)'))
'(+ 1 2)'
>>> unparse(read_one('(defn add (x y) (+ x y))'))
'(defn add (x y) (+ x y))'
>>> read_one('(defn f (x) (* x -3))')
[defn, f, [x], [*, x, -3]]        # note that -3 is an integer
>>> unparse(read_one("(if (< a 0) 'neg 'pos)"))
"(if (< a 0) (quote neg) (quote pos))"
```

The last one shows the expansion of `'`: `'neg` becomes `(quote neg)`.

Now test a real Lisp file:

```lisp
; Recursive Fibonacci
(defn fib (n)
  (if (< n 2)
      n
      (+ (fib (- n 1)) (fib (- n 2)))))
```

```python
>>> from reader import read_all
>>> forms = read_all(open('examples/fib.lisp').read())
>>> len(forms)
1
>>> forms[0]
[defn, fib, [n], [if, [<, n, 2], n, [+, [fib, [-, n, 1]], [fib, [-, n, 2]]]]]
```

**It has been read in.** Note that the `-` inside `(- n 1)` is a symbol, while `2` is an integer — the lexical rules are working correctly.

## 16.6 A Design Discussion: Why Not Do Semantic Checks in the `reader`

The `reader` only checks **syntax**:

- whether parentheses match;
- whether there are illegal characters.

It does **not** check:

- whether the parameters of a `defn` are symbols;
- whether an `if` has three arguments;
- whether a symbol has been defined.

Those are left to `compiler.py`. **Why divide it this way?**

Because syntactic and semantic errors are **different in nature**:

| | Syntax error | Semantic error |
|---|---|---|
| Example | unmatched parentheses | `if` is missing a branch |
| Decidable from the text alone? | yes | no (needs a symbol table, context) |
| Where it is checked | `reader` | `compiler` |

If the `reader` did semantic checks, it would have to know the syntactic rules of `defn`, and then the `reader` would be coupled to the language definition. **Layering exists so that each layer cares about one thing only.**

That said, `compiler.py` does contain a set of "shape checks" (you will see them in Chapters 17–19), for example:

```python
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
```

These checks run during the `compiler.collect` stage (the first pass), **before any IR has been generated**. That way the user never gets "half an IR file plus an exception".

**This principle is the same as the one explained in Section 14.7**: assert as early as possible, at the level of abstraction concerned, rather than letting illegal state flow downstream.

## 16.7 Exercises

**Exercise 16.1** Use `tokenize` to print the token sequence of `(+ 1 -2)`, and confirm that `-2` is a single `int` token.

**Exercise 16.2** Try `(- 1 -2)`. Predict the token sequence, then verify it.

**Exercise 16.3** Add a feature to the lexer: support `#` comments to the end of the line (in addition to `;`). Which lines need to change?

**Exercise 16.4** Our `read_expr` supports `'x` → `(quote x)`, but `compiler.py` does not understand `quote`. Try compiling `(defn f (x) 'x)`:

```
IRError: unknown operator or function 'quote'
```

This error is **reasonably friendly**: it names the symbol that caused the problem. But it does not give a **position** (which line and column), because we only record positions on tokens, and `Sym` does not carry one.

Directions for improvement: have `Sym` or `read_expr` attach position information to lists (for example, returning an `(expr, line, col)` tuple), or maintain a table of "symbol → position of first occurrence". This is **a problem every real compiler has to face**: how errors in the semantic analysis stage are traced back to the source.

**Exercise 16.5** Write a test case that checks whether the line and column numbers in the error message for `(foo bar` correctly point at that unclosed `(`. Then change it to `(foo\n  bar` (with a newline) — which line should the line and column numbers point at?

**Exercise 16.6 (discussion)** If our language were to support infix expressions (like C), how much code would `reader.py` need to gain? Describe (without implementing) how you would handle the precedence of `a + b * c`.

## 16.8 Summary

- The front end has two passes: **lexing** (characters → tokens) and **parsing** (tokens → S-expressions).
- The key ambiguity in lexing is `-`: **followed by a digit it is a negative integer, otherwise it is the subtraction symbol**. This is the same kind of problem as LLVM's `%1abc` in Chapter 8.
- Tokens record line and column numbers, so that error messages can point at positions in the source.
- Symbols are represented by an **interned `Sym`**, kept distinct from Python strings.
- The `reader` is only 40 lines — because S-expressions have no precedence and no ambiguity.
- `unclosed '('` reports the position of the **left parenthesis**, not the end of the file — this is a deliberate usability design.
- **Syntax is checked in the `reader`, semantics in the `compiler`.** Layering lets each layer care about one thing only.

In the next chapter we get to the core: turning S-expressions into IR.

---

<!-- nav -->
[Contents](00-preface.md) · [← Previous: Chapter 15 Language Design and Project Skeleton](15-ch15-language-design-and-skeleton.md) · [Next: Chapter 17 Code Generation: Expressions, Variables and Calls →](17-ch17-code-generation.md)
