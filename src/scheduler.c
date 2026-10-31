#include "scheduler.h"

#include <ncurses.h>
#include <stdio.h>
#include <stdlib.h>

static void schedule_next(PCB **ready, PCB **running)
{
    if (*running == NULL && *ready != NULL) {
        *running = pick_highest(ready);
        (*running)->state = STATE_RUN;
    }
}

static void advance_blocked_queue(PCB **blocked, PCB **ready)
{
    PCB *prev = NULL;
    PCB *cur = *blocked;

    while (cur != NULL) {
        PCB *next = cur->next;
        cur->io_remain -= 1;

        if (cur->io_remain <= 0) {
            if (prev == NULL) {
                *blocked = next;
            } else {
                prev->next = next;
            }
            cur->next = NULL;
            cur->state = STATE_READY;
            enqueue(ready, cur);
        } else {
            prev = cur;
        }

        cur = next;
    }
}

static void advance_running_process(PCB **running, PCB **ready,
                                    PCB **blocked, PCB **finish, int sim_sec)
{
    PCB *p = *running;

    if (p == NULL) {
        return;
    }

    p->cputime += 1;
    p->needtime -= 1;
    p->count += 1;

    if (p->needtime <= 0) {
        p->state = STATE_FINISH;
        p->finish_time = sim_sec;
        p->next = NULL;
        enqueue(finish, p);
    } else if (rand() % 100 < IO_PROB) {
        p->state = STATE_BLOCK;
        p->io_remain = IO_MIN + rand() % (IO_MAX - IO_MIN + 1);
        p->io_total += p->io_remain;
        p->next = NULL;
        enqueue(blocked, p);
    } else {
        p->prio -= RUN_PENALTY;
        p->state = STATE_READY;
        p->next = NULL;
        enqueue(ready, p);
    }

    *running = NULL;
}

static void improve_ready_priorities(PCB *ready)
{
    PCB *cur = ready;

    while (cur != NULL) {
        cur->prio += WAIT_BONUS;
        cur = cur->next;
    }
}

void run_simulation(int n_initial, unsigned seed)
{
    PCB *ready = NULL;
    PCB *running = NULL;
    PCB *blocked = NULL;
    PCB *finish = NULL;
    int pid_counter = 0;
    int sim_sec = 0;
    int total_created = 0;
    int next_arrival;

    if (n_initial < 6 || n_initial > 7) {
        fprintf(stderr, "n must be 6 or 7\n");
        return;
    }

    srand(seed);
    generate_initial(&ready, n_initial, &pid_counter);
    total_created = n_initial;
    next_arrival = ARRIVE_MIN +
                   rand() % (ARRIVE_MAX - ARRIVE_MIN + 1);

    schedule_next(&ready, &running);
    ui_init();

    for (;;) {
        int ch;

        ui_draw(ready, running, blocked, finish, sim_sec,
                next_arrival, total_created);
        ch = getch();
        if (ch == 'q' || ch == 'Q') {
            break;
        }
        if (ch != ERR) {
            continue;
        }

        ++sim_sec;
        advance_blocked_queue(&blocked, &ready);
        advance_running_process(&running, &ready, &blocked, &finish, sim_sec);
        improve_ready_priorities(ready);

        if (sim_sec >= next_arrival) {
            int count = BATCH_MIN +
                        rand() % (BATCH_MAX - BATCH_MIN + 1);
            generate_batch(&ready, count, sim_sec, &pid_counter);
            total_created += count;
            next_arrival = sim_sec + ARRIVE_MIN +
                           rand() % (ARRIVE_MAX - ARRIVE_MIN + 1);
        }

        schedule_next(&ready, &running);
    }

    ui_finalize();
    print_final_report(finish);

    destroy_queue(&ready);
    destroy_queue(&blocked);
    destroy_queue(&finish);
    free_pcb(running);
}
