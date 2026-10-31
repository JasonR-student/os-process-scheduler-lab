#include "scheduler.h"

#include <stdio.h>
#include <stdlib.h>

static void generate_processes(PCB **ready, int count, int sim_sec,
                               int *pid_counter)
{
    int i;

    for (i = 0; i < count; ++i) {
        char name[NAME_LEN];
        int needtime;
        PCB *p;

        ++(*pid_counter);
        snprintf(name, sizeof(name), "P%d", *pid_counter);
        needtime = 1 + rand() % MAX_NEEDTIME;
        p = create_pcb(name, needtime, sim_sec);
        enqueue(ready, p);
    }
}

void generate_initial(PCB **ready, int n, int *pid_counter)
{
    generate_processes(ready, n, 0, pid_counter);
}

void generate_batch(PCB **ready, int count, int sim_sec, int *pid_counter)
{
    generate_processes(ready, count, sim_sec, pid_counter);
}
