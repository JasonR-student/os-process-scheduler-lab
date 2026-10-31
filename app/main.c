#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "scheduler.h"

int main(int argc, char **argv)
{
    int n = 6;
    unsigned seed = (unsigned)time(NULL);
    int i;

    for (i = 1; i < argc; ++i) {
        if (argv[i][0] == '-' && argv[i][1] == 'n' && i + 1 < argc) {
            n = atoi(argv[++i]);
        } else if (argv[i][0] == '-' && argv[i][1] == 's' &&
                   i + 1 < argc) {
            seed = (unsigned)atoi(argv[++i]);
        }
    }

    if (n < 6 || n > 7) {
        fprintf(stderr, "Error: n must be 6 or 7 (5 < n < 8)\n");
        return EXIT_FAILURE;
    }

    run_simulation(n, seed);
    return EXIT_SUCCESS;
}
