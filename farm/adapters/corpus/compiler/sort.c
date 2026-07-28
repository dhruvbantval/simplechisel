#include <stdio.h>
int main(void) {
    int a[16] = {5, 3, 8, 1, 9, 2, 7, 4, 6, 0, 15, 11, 13, 10, 14, 12};
    int n = 16;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n - 1 - i; j++)
            if (a[j] > a[j + 1]) { int t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; }
    long checksum = 0;
    for (int i = 0; i < n; i++) { printf("%d ", a[i]); checksum = checksum * 31 + a[i]; }
    printf("\nchecksum=%ld\n", checksum);
    return 0;
}
