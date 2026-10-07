#!/usr/bin/env python3
"""End-to-end test suite for the Tiny Lisp -> LLVM IR compiler.

Every test does four things:

  1. compiles Lisp source to LLVM IR text,
  2. assembles it with `llvm-as` (which runs the LLVM verifier),
  3. links it against a C driver and runs it,
  4. compares stdout against the expected output.

Step 2 is what makes this suite worth writing: the LLVM verifier is a
merciless, third-party judge of whether the IR we generate is legal.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compiler import compile_text  # noqa: E402

LLVM_BIN = os.environ.get("LLVM_BIN", "")
CLANG = os.environ.get("CLANG", "clang-18")
LLVM_AS = os.environ.get("LLVM_AS", "llvm-as-18")


def which(name):
    path = os.path.join(LLVM_BIN, name) if LLVM_BIN else None
    if path and os.path.exists(path):
        return path
    return name


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class Case:
    def __init__(self, name, source, driver, param_types, expected, opt="", entry=None):
        self.name = name
        self.entry = entry
        self.source = source
        self.driver = driver
        self.param_types = param_types
        self.expected = expected
        self.opt = opt


CASES = []


def case(name, source, driver, param_types, expected, opt="", entry=None):
    CASES.append(Case(name, source, driver, param_types, expected, opt, entry))


# ----------------------------------------------------------------------
# 1. Straight-line arithmetic
# ----------------------------------------------------------------------
case(
    "mul_add",
    "(defn mul_add (x y z) (+ (* x y) z))",
    'printf("%d\\n", mul_add(6, 7, 3));',
    ["int", "int", "int"],
    "45\n",
)

case(
    "nested_arith",
    "(defn calc (a b c) (- (* (+ a b) c) (/ a 2)))",
    'printf("%d\\n", calc(10, 5, 4));',
    ["int", "int", "int"],
    "55\n",
)

case(
    "const_fold_shape",
    "(defn k (x) (+ x 0))",
    'printf("%d\\n", k(41));',
    ["int"],
    "41\n",
)

# ----------------------------------------------------------------------
# 2. Recursion
# ----------------------------------------------------------------------
case(
    "fib",
    """(defn fib (n)
         (if (< n 2)
             n
             (+ (fib (- n 1)) (fib (- n 2)))))""",
    'for (int i = 0; i < 12; i++) printf("%d ", fib(i));\nprintf("\\n");',
    ["int"],
    "0 1 1 2 3 5 8 13 21 34 55 89 \n",
)

case(
    "fact",
    """(defn fact (n)
         (if (<= n 1) 1 (* n (fact (- n 1)))))""",
    'printf("%d\\n", fact(10));',
    ["int"],
    "3628800\n",
)

case(
    "ackermann_ish",
    """(defn ack (m n)
         (if (= m 0) (+ n 1)
             (if (= n 0) (ack (- m 1) 1)
                 (ack (- m 1) (ack m (- n 1))))))""",
    'printf("%d\\n", ack(2, 3));',
    ["int", "int"],
    "9\n",
)

# ----------------------------------------------------------------------
# 3. Absolute value / branches producing values
# ----------------------------------------------------------------------
case(
    "abs_v",
    "(defn my_abs (x) (if (< x 0) (- 0 x) x))",
    'printf("%d %d %d\\n", my_abs(-5), my_abs(0), my_abs(7));',
    ["int"],
    "5 0 7\n",
)

case(
    "max3",
    """(defn max3 (a b c)
         (let ((m (if (> a b) a b)))
           (if (> m c) m c)))""",
    'printf("%d %d\\n", max3(1,2,3), max3(9,2,3));',
    ["int", "int", "int"],
    "3 9\n",
)

case(
    "classify",
    """(defn classify (x)
         (if (< x 0) (- 0 1)
             (if (= x 0) 0 1)))""",
    'printf("%d %d %d\\n", classify(-9), classify(0), classify(4));',
    ["int"],
    "-1 0 1\n",
)

# ----------------------------------------------------------------------
# 4. Loops and mutable state
# ----------------------------------------------------------------------
case(
    "sum_to",
    """(defn sum_to (n)
         (let ((i 1) (s 0))
           (while (<= i n)
             (set s (+ s i))
             (set i (+ i 1)))
           s))""",
    'printf("%d %d %d\\n", sum_to(0), sum_to(10), sum_to(1000));',
    ["int"],
    "0 55 500500\n",
)

case(
    "count_down",
    """(defn count_evens (n)
         (let ((i 0) (c 0))
           (while (< i n)
             (if (= (% i 2) 0) (set c (+ c 1)) 0)
             (set i (+ i 1)))
           c))""",
    'printf("%d\\n", count_evens(10));',
    ["int"],
    "5\n",
)

case(
    "nested_while",
    """(defn mult_table (n)
         (let ((i 1) (total 0))
           (while (<= i n)
             (let ((j 1))
               (while (<= j n)
                 (set total (+ total (* i j)))
                 (set j (+ j 1))))
             (set i (+ i 1)))
           total))""",
    'printf("%d\\n", mult_table(4));',
    ["int"],
    "100\n",
)

case(
    "gcd",
    """(defn gcd (a b)
         (let ((x a) (y b))
           (while (!= y 0)
             (let ((t (% x y)))
               (set x y)
               (set y t)))
           x))""",
    'printf("%d %d\\n", gcd(48, 18), gcd(270, 192));',
    ["int", "int"],
    "6 6\n",
)

# ----------------------------------------------------------------------
# 5. Calls, including forward references and declarations
# ----------------------------------------------------------------------
case(
    "mutual_helpers",
    """(defn dbl (x) (* x 2))
       (defn quad (x) (dbl (dbl x)))
       (defn calc (x) (+ (quad x) (dbl x)))""",
    'printf("%d\\n", calc(5));',
    ["int"],
    "30\n",
    entry="calc",
)

case(
    "forward_ref",
    """(defn outer (x) (inner (+ x 1)))
       (defn inner (y) (* y 10))""",
    'printf("%d\\n", outer(4));',
    ["int"],
    "50\n",
)

case(
    "extern_call",
    """(declare ext_abs (x))
       (defn use_ext (x) (+ (ext_abs x) 1))""",
    'printf("%d\\n", use_ext(-33));',
    ["int"],
    "34\n",
    opt="extern",
)

# ----------------------------------------------------------------------
# 6. Optimised builds must behave identically
# ----------------------------------------------------------------------
for optlevel in ("-O1", "-O2", "-O3"):
    CASES.append(
        Case(
            f"fib_{optlevel}",
            """(defn fib (n)
                 (if (< n 2) n
                     (+ (fib (- n 1)) (fib (- n 2)))))""",
            'printf("%d\\n", fib(20));',
            ["int"],
            "6765\n",
            opt=optlevel,
        )
    )
    CASES.append(
        Case(
            f"sum_to_{optlevel}",
            """(defn sum_to (n)
                 (let ((i 1) (s 0))
                   (while (<= i n)
                     (set s (+ s i))
                     (set i (+ i 1)))
                   s))""",
            'printf("%d\\n", sum_to(1000));',
            ["int"],
            "500500\n",
            opt=optlevel,
        )
    )


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------
EXT_SOURCE = (
    "#include <stdlib.h>\n"
    "/* Declared in Lisp as (declare ext_abs (x)); the symbol is mangled\n"
    "   to l_ext_abs just like user-defined functions. */\n"
    "int l_ext_abs(int x) { return abs(x); }\n"
)


def build_and_run(case_obj, workdir):
    """Return (ok, detail)."""
    try:
        module = compile_text(case_obj.source)
    except Exception as exc:  # noqa: BLE001
        return False, f"compile error: {exc}"

    ll_text = module.render(triple="x86_64-pc-linux-gnu")
    ll_path = os.path.join(workdir, f"{case_obj.name}.ll")
    bc_path = os.path.join(workdir, f"{case_obj.name}.bc")
    with open(ll_path, "w") as fh:
        fh.write(ll_text)

    # Step 2: the verifier.  This is the real test.
    res = run([which(LLVM_AS), ll_path, "-o", bc_path])
    if res.returncode != 0:
        return False, f"llvm-as rejected the IR:\n{res.stderr.strip()}"

    # Step 3: a C driver calls into the generated code.
    driver = "#include <stdio.h>\n"
    if case_obj.opt == "extern":
        driver += EXT_SOURCE
    # The test body calls unmangled names; alias them so the cases read
    # like the Lisp they came from.  The macros come first so that the
    # prototype below survives preprocessing intact.
    for user_name in _all_defn_names(case_obj.source):
        driver += f"#define {user_name} l_{user_name}\n"
    # Prototype the *unmangled* name, so that the macros above rewrite it
    # to the real (mangled) symbol exactly once.
    driver += "int %s(%s);\n" % (
        _entry_name(case_obj)[len("l_"):],
        ", ".join(case_obj.param_types),
    )
    driver += "int main(void) {\n  " + case_obj.driver + "\n  return 0;\n}\n"
    c_path = os.path.join(workdir, f"{case_obj.name}.c")
    exe_path = os.path.join(workdir, case_obj.name)
    with open(c_path, "w") as fh:
        fh.write(driver)

    optflags = []
    if case_obj.opt and case_obj.opt.startswith("-O"):
        optflags = [case_obj.opt]
    cmd = [CLANG, "-w", *optflags, c_path, bc_path, "-o", exe_path]
    if case_obj.opt == "extern":
        cmd = [CLANG, "-w", c_path, bc_path, "-o", exe_path]
    res = run(cmd)
    if res.returncode != 0:
        return False, f"clang failed:\n{res.stderr.strip()}"

    res = run([exe_path])
    if res.returncode != 0:
        return False, f"program exited {res.returncode}\n{res.stderr.strip()}"
    if res.stdout != case_obj.expected:
        return False, f"expected {case_obj.expected!r}, got {res.stdout!r}"
    return True, "ok"



def _all_defn_names(source):
    names = []
    for line in source.splitlines():
        line = line.strip()
        if line.startswith("(defn "):
            names.append(line.split()[1])
    return names


def _entry_name(case_obj):
    """The Lisp function the driver should call, with an `l_` prefix.

    The prefix matters: Lisp identifiers such as `double` or `abs` are
    perfectly good Lisp names but collide with names from <stdio.h> and
    <stdlib.h>.  Mangling user names on the way out is standard practice
    for real compilers, and we adopt it here.
    """
    if case_obj.entry:
        return "l_" + case_obj.entry
    for line in case_obj.source.splitlines():
        line = line.strip()
        if line.startswith("(defn "):
            return "l_" + line.split()[1]
    raise AssertionError("no defn found")


def main():
    keep = "--keep" in sys.argv
    workdir = tempfile.mkdtemp(prefix="lispc-test-")
    passed = 0
    failed = []
    for c in CASES:
        ok, detail = build_and_run(c, workdir)
        label = c.name + (f" [{c.opt}]" if c.opt else "")
        if ok:
            passed += 1
            print(f"PASS  {label}")
        else:
            failed.append((label, detail))
            print(f"FAIL  {label}: {detail}")

    print()
    print(f"{passed}/{len(CASES)} passed")
    if failed:
        print("\nFailures:")
        for label, detail in failed:
            print(f"  {label}: {detail}")
    if not keep:
        subprocess.run(["rm", "-rf", workdir])
    else:
        print(f"artifacts kept in {workdir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
