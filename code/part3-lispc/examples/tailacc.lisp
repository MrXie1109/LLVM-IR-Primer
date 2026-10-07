; Tail-recursive accumulator sum: LLVM's tailcallelim should turn this
; into a loop, then loop-idiom may even produce the closed form.
(defn sum_acc (n acc)
  (if (= n 0)
      acc
      (sum_acc (- n 1) (+ acc n))))
