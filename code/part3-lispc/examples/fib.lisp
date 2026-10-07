; Recursive Fibonacci: the classic first LLVM IR program.
(defn fib (n)
  (if (< n 2)
      n
      (+ (fib (- n 1)) (fib (- n 2)))))
