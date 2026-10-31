#include "scheduler.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

PCB *create_pcb(const char *name, int needtime, int arrival_time)
{
    PCB *p = malloc(sizeof(*p));
    if (p == NULL) {
        fprintf(stderr, "malloc failed while creating PCB\n");
        exit(EXIT_FAILURE);
    }

    strncpy(p->name, name, NAME_LEN - 1);
    p->name[NAME_LEN - 1] = '\0';
    p->prio = BASE_PRIO - needtime;
    p->round = TIME_SLICE;
    p->cputime = 0;
    p->needtime = needtime;
    p->count = 0;
    p->state = STATE_READY;
    p->next = NULL;
    p->arrival_time = arrival_time;
    p->io_remain = 0;
    p->io_total = 0;
    p->finish_time = 0;

    return p;
}

void free_pcb(PCB *p)
{
    free(p);
}
