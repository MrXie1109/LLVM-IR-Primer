@pub_global = global i32 1
@priv_global = private global i32 2
@internal_global = internal global i32 3
@weak_global = weak global i32 4
@common_global = common global i32 0
@ext_global = external global i32
@const_global = constant i32 5
@thread_local_g = thread_local global i32 6

define i32 @pub_fn() { ret i32 0 }
define private i32 @priv_fn() { ret i32 0 }
define internal i32 @int_fn() { ret i32 0 }
define weak i32 @weak_fn() { ret i32 0 }
define linkonce_odr i32 @lodr_fn() { ret i32 0 }
