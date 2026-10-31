#ifndef SCHEDULER_H
#define SCHEDULER_H

#define NAME_LEN      10
#define TIME_SLICE    1
#define BASE_PRIO     50
#define RUN_PENALTY   3
#define WAIT_BONUS    1
#define MAX_NEEDTIME  20
#define IO_PROB       20
#define IO_MIN        1
#define IO_MAX        3
#define ARRIVE_MIN    1
#define ARRIVE_MAX    10
#define BATCH_MIN     1
#define BATCH_MAX     3

#define STATE_READY   'W'
#define STATE_RUN     'R'
#define STATE_BLOCK   'B'
#define STATE_FINISH  'F'

typedef struct node PCB;
struct node {
    char name[NAME_LEN];
    int prio;
    int round;
    int cputime;
    int needtime;
    int count;
    char state;
    PCB *next;
    int arrival_time;
    int io_remain;
    int io_total;
    int finish_time;
};

PCB *create_pcb(const char *name, int needtime, int arrival_time);
void free_pcb(PCB *p);

void enqueue(PCB **head, PCB *p);
PCB *dequeue(PCB **head);
PCB *pick_highest(PCB **head);
int queue_length(PCB *head);
void destroy_queue(PCB **head);

void generate_initial(PCB **ready, int n, int *pid_counter);
void generate_batch(PCB **ready, int count, int sim_sec, int *pid_counter);

void run_simulation(int n_initial, unsigned seed);

void ui_init(void);
void ui_draw(const PCB *ready, const PCB *running, const PCB *blocked,
             const PCB *finish, int sim_sec, int next_arrival,
             int total_created);
void ui_finalize(void);
void print_final_report(const PCB *finish);

#endif
