#include "scheduler.h"

#include <stddef.h>

void enqueue(PCB **head, PCB *p)
{
    PCB *cur;

    if (head == NULL || p == NULL) {
        return;
    }

    p->next = NULL;
    if (*head == NULL) {
        *head = p;
        return;
    }

    cur = *head;
    while (cur->next != NULL) {
        cur = cur->next;
    }
    cur->next = p;
}

PCB *dequeue(PCB **head)
{
    PCB *p;

    if (head == NULL || *head == NULL) {
        return NULL;
    }

    p = *head;
    *head = p->next;
    p->next = NULL;
    return p;
}

PCB *pick_highest(PCB **head)
{
    PCB *best;
    PCB *best_prev;
    PCB *prev;
    PCB *cur;

    if (head == NULL || *head == NULL) {
        return NULL;
    }

    best = *head;
    best_prev = NULL;
    prev = *head;
    cur = (*head)->next;

    while (cur != NULL) {
        if (cur->prio > best->prio) {
            best = cur;
            best_prev = prev;
        }
        prev = cur;
        cur = cur->next;
    }

    if (best_prev == NULL) {
        *head = best->next;
    } else {
        best_prev->next = best->next;
    }
    best->next = NULL;
    return best;
}

int queue_length(PCB *head)
{
    int count = 0;
    PCB *cur = head;

    while (cur != NULL) {
        ++count;
        cur = cur->next;
    }
    return count;
}

void destroy_queue(PCB **head)
{
    PCB *p;

    if (head == NULL) {
        return;
    }

    while ((p = dequeue(head)) != NULL) {
        free_pcb(p);
    }
}
