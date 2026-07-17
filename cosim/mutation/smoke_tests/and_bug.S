.globl _start
_start:
    lui  x5, 0x55555
    lui  x6, 0x0f0f0
    and  x7, x5, x6
    j    .
