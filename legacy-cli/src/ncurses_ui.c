#include "scheduler.h"

#include <ncurses.h>
#include <stdio.h>

static int ui_started;
static int color_enabled;

static int count_nodes(const PCB *head)
{
    int count = 0;
    const PCB *cur = head;

    while (cur != NULL) {
        ++count;
        cur = cur->next;
    }
    return count;
}

static void draw_text(int row, int col, int width, const char *text,
                      int color_pair, int bold)
{
    int available;

    if (!ui_started || row < 0 || col < 0 || row >= LINES || col >= COLS) {
        return;
    }

    available = COLS - col - 1;
    if (width > available) {
        width = available;
    }
    if (width <= 0) {
        return;
    }

    if (color_enabled && color_pair > 0) {
        attron(COLOR_PAIR(color_pair));
    }
    if (bold) {
        attron(A_BOLD);
    }
    mvaddnstr(row, col, text, width);
    if (bold) {
        attroff(A_BOLD);
    }
    if (color_enabled && color_pair > 0) {
        attroff(COLOR_PAIR(color_pair));
    }
}

static void draw_ready_queue(const PCB *ready, int row, int col, int width,
                             int bottom)
{
    const PCB *cur = ready;

    while (cur != NULL && row < bottom) {
        char line[80];
        snprintf(line, sizeof(line), "%s prio=%d need=%d",
                 cur->name, cur->prio, cur->needtime);
        draw_text(row, col, width, line, 1, 0);
        ++row;
        cur = cur->next;
    }
}

static void draw_running_process(const PCB *running, int row, int col,
                                 int width)
{
    char line[120];

    if (running == NULL) {
        draw_text(row, col, width, "IDLE", 0, 1);
        return;
    }

    snprintf(line, sizeof(line), "%s prio=%d cpu=%d need=%d count=%d",
             running->name, running->prio, running->cputime,
             running->needtime, running->count);
    draw_text(row, col, width, line, 2, 1);
}

static void draw_blocked_queue(const PCB *blocked, int row, int col, int width,
                               int bottom)
{
    const PCB *cur = blocked;

    while (cur != NULL && row < bottom) {
        char line[80];
        snprintf(line, sizeof(line), "%s io_remain=%ds",
                 cur->name, cur->io_remain);
        draw_text(row, col, width, line, 3, 0);
        ++row;
        cur = cur->next;
    }
}

static void draw_finish_summary(const PCB *finish, int row, int col, int width)
{
    const PCB *cur = finish;
    int count = 0;
    double total_turnaround = 0.0;
    char line[120];

    while (cur != NULL) {
        total_turnaround += cur->finish_time - cur->arrival_time;
        ++count;
        cur = cur->next;
    }

    snprintf(line, sizeof(line), "finished=%d avg_turnaround=%.2f",
             count, count == 0 ? 0.0 : total_turnaround / count);
    draw_text(row, col, width, line, 4, 0);
}

void ui_init(void)
{
    initscr();
    ui_started = 1;
    cbreak();
    noecho();
    keypad(stdscr, TRUE);
    curs_set(0);
    timeout(1000);

    if (has_colors()) {
        start_color();
        init_pair(1, COLOR_BLUE, COLOR_BLACK);
        init_pair(2, COLOR_GREEN, COLOR_BLACK);
        init_pair(3, COLOR_YELLOW, COLOR_BLACK);
        init_pair(4, COLOR_WHITE, COLOR_BLACK);
        color_enabled = 1;
    }
}

void ui_draw(const PCB *ready, const PCB *running, const PCB *blocked,
             const PCB *finish, int sim_sec, int next_arrival,
             int total_created)
{
    int height;
    int width;
    int left_width;
    int middle_width;
    int right_width;
    int middle_col;
    int right_col;
    int bottom;
    char status[180];

    if (!ui_started) {
        return;
    }

    erase();
    getmaxyx(stdscr, height, width);
    if (height < 24 || width < 80) {
        draw_text(0, 0, width, "Terminal window too small (minimum 80x24)",
                  0, 1);
        refresh();
        return;
    }

    snprintf(status, sizeof(status),
             "time=%ds | total=%d | R=%d W=%d B=%d F=%d | next arrive=%ds | press q to quit",
             sim_sec, total_created, running == NULL ? 0 : 1,
             count_nodes(ready), count_nodes(blocked), count_nodes(finish),
             next_arrival);
    draw_text(0, 0, width, status, 0, 1);
    mvhline(1, 0, ACS_HLINE, width);

    left_width = width * 30 / 100;
    middle_width = width * 35 / 100;
    right_width = width - left_width - middle_width;
    middle_col = left_width;
    right_col = left_width + middle_width;
    bottom = height - 5;

    draw_text(2, 0, left_width, "READY [W]", 1, 1);
    draw_text(2, middle_col, middle_width, "RUNNING [R]", 2, 1);
    draw_text(2, right_col, right_width, "BLOCKED [B]", 3, 1);
    draw_ready_queue(ready, 3, 0, left_width, bottom);
    draw_running_process(running, 3, middle_col, middle_width);
    draw_blocked_queue(blocked, 3, right_col, right_width, bottom);

    mvhline(height - 4, 0, ACS_HLINE, width);
    draw_text(height - 3, 0, width, "FINISHED [F]", 4, 1);
    draw_finish_summary(finish, height - 2, 0, width);
    refresh();
}

void ui_finalize(void)
{
    if (ui_started) {
        endwin();
        ui_started = 0;
    }
}

void print_final_report(const PCB *finish)
{
    const PCB *cur = finish;
    int count = 0;
    double total_turnaround = 0.0;
    double total_wait = 0.0;
    double total_weighted = 0.0;

    printf("\nFinal process report\n");
    printf("%-8s %8s %8s %8s %8s %8s %8s %10s\n",
           "Name", "Arrival", "Finish", "CPU", "IO", "Turnaround",
           "Wait", "Weighted");

    while (cur != NULL) {
        int turnaround = cur->finish_time - cur->arrival_time;
        int wait_time = turnaround - cur->cputime - cur->io_total;
        double weighted = (double)turnaround / cur->cputime;

        printf("%-8s %8d %8d %8d %8d %8d %8d %10.2f\n",
               cur->name, cur->arrival_time, cur->finish_time,
               cur->cputime, cur->io_total, turnaround, wait_time, weighted);
        total_turnaround += turnaround;
        total_wait += wait_time;
        total_weighted += weighted;
        ++count;
        cur = cur->next;
    }

    if (count == 0) {
        printf("No completed processes\n");
        return;
    }

    printf("\nCompleted processes: %d\n", count);
    printf("Average turnaround: %.2f\n", total_turnaround / count);
    printf("Average wait: %.2f\n", total_wait / count);
    printf("Average weighted turnaround: %.2f\n",
           total_weighted / count);
}
