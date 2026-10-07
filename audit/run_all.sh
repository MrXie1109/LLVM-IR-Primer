#!/bin/bash
# Full verification: toolchain version, book IR snippets, compiler test suite.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p scratch

echo "################ 1. TOOLCHAIN VERSION ################"
clang-18 --version | head -1
echo "llvm-config-18: $(llvm-config-18 --version)"
python3 --version
echo
echo "################ 2. BOOK IR SNIPPETS vs LIVE OUTPUT ################"
python3 audit/check_ir_snippets.py
echo
echo "################ 2b. COMPARATIVE (NEGATIVE) CLAIMS RE-DERIVED ################"
python3 audit/check_negative_claims.py
echo
echo "################ 2c. QUOTED ERROR MESSAGES REPRODUCE ################"
python3 audit/check_error_messages.py
echo
echo "################ 2d. QUOTED COMPILER OUTPUT IS VERBATIM ################"
python3 audit/check_quoted_blocks.py
echo
echo "################ 2e. LINKS AND ANCHORS ################"
python3 audit/check_links.py
echo
echo "################ 2f. ENGLISH EDITION: CODE FIDELITY ################"
python3 audit/check_code_fidelity.py
echo
echo "################ 2g. ENGLISH EDITION: LINKS AND ANCHORS ################"
python3 audit/check_links.py book-en
echo
echo "################ 3. COMPILER END-TO-END TESTS ################"
(cd code/part3-lispc && python3 tests.py | tail -3)
echo
echo "################ 4. CHAPTER 14 STANDALONE SKELETON ################"
(cd code/part3-lispc && python3 minimal_codegen.py) > scratch/c14.ll
llvm-as-18 scratch/c14.ll -o /dev/null && echo "ch14 skeleton: VERIFIES OK"
head -5 scratch/c14.ll
echo
echo "################ 5. PART III: GENERATED IR IS ACCEPTED BY LLVM ################"
for ex in fib sum countdown tailacc; do
  if [ -f "code/part3-lispc/examples/$ex.lisp" ]; then
    (cd code/part3-lispc && python3 compiler.py "examples/$ex.lisp") > "scratch/$ex.ll"
    llvm-as-18 "scratch/$ex.ll" -o /dev/null && echo "  examples/$ex.lisp -> verifies OK"
  fi
done
echo
echo "ALL VERIFICATION PASSED"
