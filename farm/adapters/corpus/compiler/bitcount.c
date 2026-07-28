#include <stdio.h>
static int popcount(unsigned x) { int c = 0; while (x) { c += x & 1u; x >>= 1; } return c; }
int main(void) {
    unsigned long sum = 0;
    for (unsigned x = 0; x < 100000u; x++) sum += (unsigned)popcount(x);
    printf("total set bits 0..99999 = %lu\n", sum);
    return 0;
}
