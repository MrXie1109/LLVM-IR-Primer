; Sum 1..n with an explicit loop, using a mutable accumulator.
(defn sum_to (n)
  (let ((i 1) (s 0))
    (while (<= i n)
      (let ((tmp (+ s i)))
        (set s tmp))
      (set i (+ i 1)))
    s))
