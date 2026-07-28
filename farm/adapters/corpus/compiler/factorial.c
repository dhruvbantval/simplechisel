#include <stdio.h>
static unsigned long fact(unsigned n) { return n < 2 ? 1UL : n * fact(n - 1); }
int main(void) {
    for (unsigned i = 0; i <= 12; i++) printf("%u! = %lu\n", i, fact(i));
    return 0;
}
