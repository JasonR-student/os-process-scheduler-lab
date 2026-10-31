CC ?= gcc
CFLAGS ?= -Wall -Wextra -std=c11 -O2

.PHONY: all clean

all: scheduler-worker

scheduler-worker: worker.c
	$(CC) $(CFLAGS) worker.c -o scheduler-worker

clean:
	rm -f scheduler-worker
