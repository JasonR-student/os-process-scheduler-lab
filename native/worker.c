#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static long long monotonic_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL;
}

static void busy_wait_ms(int duration_ms)
{
    volatile unsigned long counter = 0;
    long long deadline = monotonic_ms() + duration_ms;

    while (monotonic_ms() < deadline) {
        counter = counter * 1664525UL + 1013904223UL;
    }
    (void)counter;
}

static void print_event(const char *event)
{
    printf("%s %ld\n", event, (long)getpid());
    fflush(stdout);
}

int main(int argc, char **argv)
{
    char command[128];
    const char *name = "worker";
    int i;

    for (i = 1; i + 1 < argc; ++i) {
        if (strcmp(argv[i], "--name") == 0) {
            name = argv[++i];
        }
    }

    setvbuf(stdout, NULL, _IOLBF, 0);
    printf("READY %ld %s\n", (long)getpid(), name);
    fflush(stdout);

    while (fgets(command, sizeof(command), stdin) != NULL) {
        int duration_ms = 0;
        int io_seconds = 0;
        char action[16] = {0};

        if (strncmp(command, "EXIT", 4) == 0) {
            print_event("EXIT");
            return EXIT_SUCCESS;
        }

        if (strncmp(command, "RESUME", 6) == 0) {
            print_event("IO_RESUMED");
            continue;
        }

        if (sscanf(command, "RUN %d %15s %d",
                   &duration_ms, action, &io_seconds) != 3) {
            fprintf(stderr, "invalid command: %s", command);
            continue;
        }

        if (duration_ms < 1) {
            duration_ms = 1;
        }
        busy_wait_ms(duration_ms);

        if (strcmp(action, "FINISH") == 0) {
            print_event("FINISHED");
            return EXIT_SUCCESS;
        }
        if (strcmp(action, "IO") == 0) {
            printf("IO_REQUEST %ld %d\n", (long)getpid(), io_seconds);
            fflush(stdout);
            while (fgets(command, sizeof(command), stdin) != NULL) {
                if (strncmp(command, "RESUME", 6) == 0) {
                    print_event("IO_RESUMED");
                    break;
                }
                if (strncmp(command, "EXIT", 4) == 0) {
                    return EXIT_SUCCESS;
                }
            }
            continue;
        }

        print_event("CPU_SLICE_DONE");
    }

    if (errno != 0 && errno != EINTR) {
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
