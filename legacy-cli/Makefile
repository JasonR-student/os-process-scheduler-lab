CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -Iinclude -fPIC

.PHONY: all clean

all: libscheduler.so main

libscheduler.so: src/*.c include/scheduler.h
	$(CC) $(CFLAGS) -shared src/*.c -o libscheduler.so -lncurses

main: app/main.c libscheduler.so
	$(CC) app/main.c -Iinclude -L. -lscheduler -lncurses -o main \
		-Wl,-rpath,'$$ORIGIN'

clean:
	rm -f libscheduler.so main
