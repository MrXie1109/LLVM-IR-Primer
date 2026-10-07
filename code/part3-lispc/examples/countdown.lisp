; Tail-recursive countdown: tests whether LLVM turns tail calls into loops.
(defn count_down (n)
  (if (= n 0)
      0
      (count_down (- n 1))))
