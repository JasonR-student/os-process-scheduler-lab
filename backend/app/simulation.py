from __future__ import annotations

import asyncio
import csv
import copy
import io
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .models import ProcessView, SessionConfig


@dataclass
class SimProcess:
    name: str
    needtime: int
    arrival_time: int
    prio: int
    pid: int | None = None
    ppid: int | None = None
    pgid: int | None = None
    linux_state: str | None = None
    rss_kb: int | None = None
    voluntary_ctxt_switches: int | None = None
    nonvoluntary_ctxt_switches: int | None = None
    fd_count: int | None = None
    started_at: str | None = None
    state: str = "W"
    cputime: int = 0
    count: int = 0
    io_remain: int = 0
    io_total: int = 0
    finish_time: int = 0
    context_switches: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def view(self) -> dict[str, Any]:
        return ProcessView(
            name=self.name,
            pid=self.pid,
            ppid=self.ppid,
            pgid=self.pgid,
            state=self.state,
            linux_state=self.linux_state,
            prio=self.prio,
            needtime=self.needtime,
            cputime=self.cputime,
            count=self.count,
            arrival_time=self.arrival_time,
            io_remain=self.io_remain,
            io_total=self.io_total,
            finish_time=self.finish_time,
            context_switches=self.context_switches,
            rss_kb=self.rss_kb,
            voluntary_ctxt_switches=self.voluntary_ctxt_switches,
            nonvoluntary_ctxt_switches=self.nonvoluntary_ctxt_switches,
            fd_count=self.fd_count,
            started_at=self.started_at,
            history=self.history[-12:],
        ).model_dump()


class SimulationSession:
    """Deterministic user-space model of the course scheduling algorithm."""

    def __init__(self, config: SessionConfig, session_id: str | None = None):
        self.id = session_id or uuid.uuid4().hex[:12]
        self.config = config
        self.mode = "simulation"
        self.status = "ready"
        self.now = 0
        self.seq = 0
        self.pid_counter = 0
        self.total_created = 0
        self.context_switches = 0
        self.next_arrival = 0
        self.rng = random.Random(config.seed)
        self.processes: dict[str, SimProcess] = {}
        self.ready: list[str] = []
        self.blocked: list[str] = []
        self.finished: list[str] = []
        self.running: str | None = None
        self.event_history: list[dict[str, Any]] = []
        self.gantt: list[dict[str, Any]] = []
        self.priority_history: dict[str, list[dict[str, int]]] = {}
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.runner_task: asyncio.Task[None] | None = None
        self.undo_stack: list[dict[str, Any]] = []
        self._reset_state()

    def _reset_state(self) -> None:
        self.now = 0
        self.seq = 0
        self.pid_counter = 0
        self.total_created = 0
        self.context_switches = 0
        self.next_arrival = self._random_arrival()
        self.processes.clear()
        self.ready.clear()
        self.blocked.clear()
        self.finished.clear()
        self.running = None
        self.event_history.clear()
        self.gantt.clear()
        self.priority_history.clear()
        self.undo_stack.clear()
        self.status = "ready"
        self._create_batch(self.config.initial_processes, 0)
        self._schedule_next()
        self._record_event(
            "session_started",
            {
                "message": "Deterministic simulation initialized",
                "seed": self.config.seed,
            },
        )

    def _random_arrival(self) -> int:
        return self.rng.randint(self.config.arrival_min, self.config.arrival_max)

    def _create_batch(self, count: int, arrival_time: int) -> None:
        if self.config.continuous:
            count = min(count, self.config.max_processes - len(self.processes))
        for _ in range(count):
            if not self.config.continuous and self.total_created >= self.config.max_processes:
                return
            self.pid_counter += 1
            name = f"P{self.pid_counter}"
            needtime = self.rng.randint(1, 20)
            process = SimProcess(
                name=name,
                needtime=needtime,
                arrival_time=arrival_time,
                prio=50 - needtime,
                pid=1000 + self.pid_counter,
            )
            process.history.append(
                {"time": arrival_time, "state": "W", "reason": "created"}
            )
            self.processes[name] = process
            self.ready.append(name)
            self.priority_history[name] = [
                {"time": arrival_time, "prio": process.prio}
            ]
            self.total_created += 1
            self._record_event(
                "process_created",
                {"process": process.view(), "reason": "arrival"},
            )

    def _prune_finished(self) -> None:
        if not self.config.continuous:
            return
        while len(self.finished) > 24:
            name = self.finished.pop(0)
            self.processes.pop(name, None)
            self.priority_history.pop(name, None)

    def _schedule_next(self) -> None:
        if self.running is not None or not self.ready:
            return
        self.ready.sort(
            key=lambda name: (
                -self.processes[name].prio,
                self.processes[name].arrival_time,
                name,
            )
        )
        name = self.ready.pop(0)
        process = self.processes[name]
        process.state = "R"
        process.context_switches += 1
        process.history.append(
            {"time": self.now, "state": "R", "reason": "dispatch"}
        )
        self.running = name
        self.context_switches += 1
        self._record_event(
            "process_scheduled",
            {"process": process.view(), "reason": "highest-priority-ready"},
        )

    def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.seq += 1
        event = {
            "type": event_type,
            "seq": self.seq,
            "time": self.now,
            "mode": self.mode,
            "payload": payload,
        }
        self.event_history.append(event)
        self.event_history = self.event_history[-200:]
        for queue in tuple(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.subscribers.add(queue)
        queue.put_nowait(self._snapshot_event())
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)

    def _snapshot_event(self) -> dict[str, Any]:
        self.seq += 1
        return {
            "type": "snapshot",
            "seq": self.seq,
            "time": self.now,
            "mode": self.mode,
            "payload": self.snapshot(),
        }

    def snapshot(self) -> dict[str, Any]:
        processes = [process.view() for process in self.processes.values()]
        running_process = (
            self.processes[self.running] if self.running else None
        )
        return {
            "session_id": self.id,
            "status": self.status,
            "time": self.now,
            "cpu_time": self.now,
            "time_slice": self.config.time_slice,
            "running_cpu_time": running_process.cputime if running_process else 0,
            "mode": self.mode,
            "next_arrival": self.next_arrival,
            "created": self.total_created,
            "context_switches": self.context_switches,
            "cpu_utilization": 100 if self.running else 0,
            "queue_counts": {
                "ready": len(self.ready),
                "running": 1 if self.running else 0,
                "blocked": len(self.blocked),
                "finished": len(self.finished),
            },
            "running": running_process.view() if running_process else None,
            "ready": [self.processes[name].view() for name in self.ready],
            "blocked": [self.processes[name].view() for name in self.blocked],
            "finished": [
                self.processes[name].view() for name in self.finished
            ],
            "processes": processes,
            "events": [
                event
                for event in self.event_history
                if event["type"] != "snapshot"
            ][-40:],
            "gantt": self.gantt[-120:],
            "priority_history": self.priority_history,
        }

    def _record_priority(self, process: SimProcess) -> None:
        self.priority_history.setdefault(process.name, []).append(
            {"time": self.now, "prio": process.prio}
        )

    def _capture_state(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "now": self.now,
                "seq": self.seq,
                "pid_counter": self.pid_counter,
                "total_created": self.total_created,
                "context_switches": self.context_switches,
                "next_arrival": self.next_arrival,
                "rng_state": self.rng.getstate(),
                "processes": self.processes,
                "ready": self.ready,
                "blocked": self.blocked,
                "finished": self.finished,
                "running": self.running,
                "event_history": self.event_history,
                "gantt": self.gantt,
                "priority_history": self.priority_history,
                "status": self.status,
            }
        )

    def _restore_state(self, state: dict[str, Any]) -> None:
        self.now = state["now"]
        self.seq = state["seq"]
        self.pid_counter = state["pid_counter"]
        self.total_created = state["total_created"]
        self.context_switches = state["context_switches"]
        self.next_arrival = state["next_arrival"]
        self.rng.setstate(state["rng_state"])
        self.processes = state["processes"]
        self.ready = state["ready"]
        self.blocked = state["blocked"]
        self.finished = state["finished"]
        self.running = state["running"]
        self.event_history = state["event_history"]
        self.gantt = state["gantt"]
        self.priority_history = state["priority_history"]
        self.status = "paused"

    def step(self) -> dict[str, Any]:
        if self.status in {"stopped", "completed"}:
            return self.snapshot()

        self.undo_stack.append(self._capture_state())
        self.undo_stack = self.undo_stack[-240:]
        was_playing = self.status == "running"
        self.status = "running"
        self.now += self.config.time_slice

        # 1. Complete one second of I/O before running the CPU process.
        for name in list(self.blocked):
            process = self.processes[name]
            process.io_remain -= self.config.time_slice
            if process.io_remain <= 0:
                self.blocked.remove(name)
                process.state = "W"
                process.history.append(
                    {"time": self.now, "state": "W", "reason": "io-complete"}
                )
                self.ready.append(name)
                self._record_event(
                    "process_woken",
                    {"process": process.view(), "reason": "io-complete"},
                )

        waiting_names = list(self.ready)

        # 2. Consume one time slice for the running process.
        running_name = self.running
        if running_name is not None:
            process = self.processes[running_name]
            process.cputime += self.config.time_slice
            process.needtime -= self.config.time_slice
            process.count += 1
            self.gantt.append(
                {
                    "time": self.now,
                    "process": process.name,
                    "state": "R",
                    "reason": "time-slice",
                }
            )
            self.running = None

            if process.needtime <= 0:
                process.needtime = 0
                process.state = "F"
                process.finish_time = self.now
                process.history.append(
                    {"time": self.now, "state": "F", "reason": "needtime-zero"}
                )
                self.finished.append(process.name)
                self._record_event(
                    "process_finished",
                    {"process": process.view(), "reason": "needtime-zero"},
                )
            elif self.rng.randrange(100) < self.config.io_probability:
                process.state = "B"
                process.io_remain = self.rng.randint(
                    self.config.io_min, self.config.io_max
                )
                process.io_total += process.io_remain
                process.history.append(
                    {"time": self.now, "state": "B", "reason": "io-request"}
                )
                self.blocked.append(process.name)
                self._record_event(
                    "process_blocked",
                    {"process": process.view(), "reason": "io-request"},
                )
            else:
                process.prio -= 3
                process.state = "W"
                process.history.append(
                    {"time": self.now, "state": "W", "reason": "preempted"}
                )
                self.ready.append(process.name)
                self._record_event(
                    "process_preempted",
                    {"process": process.view(), "reason": "time-slice-end"},
                )
            self._record_priority(process)

        # 3. Age processes that were already waiting at tick start.
        for name in waiting_names:
            process = self.processes[name]
            process.prio += 1
            self._record_priority(process)

        # 4. Generate a new batch, without an immediate waiting bonus.
        if (
            (self.config.continuous or self.total_created < self.config.max_processes)
            and self.now >= self.next_arrival
        ):
            count = self.rng.randint(self.config.batch_min, self.config.batch_max)
            if not self.config.continuous:
                count = min(count, self.config.max_processes - self.total_created)
            self._create_batch(count, self.now)
            self.next_arrival = self.now + self._random_arrival()

        # 5. Dispatch the next process.
        self._schedule_next()

        if (
            not self.config.continuous
            and self.total_created >= self.config.max_processes
            and not self.ready
            and not self.blocked
            and self.running is None
        ):
            self.status = "completed"
            self._record_event(
                "report_ready", {"message": "All configured processes finished"}
            )
        elif not was_playing:
            self.status = "paused"

        self._prune_finished()
        self._record_event("snapshot", self.snapshot())
        return self.snapshot()

    def back(self) -> dict[str, Any]:
        if self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()
        if not self.undo_stack:
            return self.snapshot()
        self._restore_state(self.undo_stack.pop())
        self._record_event("session_rewound", {"message": "Moved one simulation tick backward"})
        self._record_event("snapshot", self.snapshot())
        return self.snapshot()

    async def play(self) -> None:
        while self.status == "running":
            self.step()
            await asyncio.sleep(self.config.tick_ms / 1000)

    async def start(self) -> dict[str, Any]:
        if self.status == "completed":
            return self.snapshot()
        self.status = "running"
        if self.runner_task is None or self.runner_task.done():
            self.runner_task = asyncio.create_task(self.play())
        self._record_event("session_started", {"message": "Playback started"})
        return self.snapshot()

    async def pause(self) -> dict[str, Any]:
        self.status = "paused"
        self._record_event("session_paused", {"message": "Playback paused"})
        return self.snapshot()

    async def reset(self) -> dict[str, Any]:
        if self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()
        self.rng = random.Random(self.config.seed)
        self._reset_state()
        if self.config.continuous:
            self.status = "running"
            self.runner_task = asyncio.create_task(self.play())
        self._record_event("session_reset", {"message": "Session reset"})
        return self.snapshot()

    async def stop(self) -> dict[str, Any]:
        self.status = "stopped"
        if self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()
        self._record_event("session_stopped", {"message": "Session stopped"})
        return self.snapshot()

    def report(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for name in self.finished:
            process = self.processes[name]
            turnaround = process.finish_time - process.arrival_time
            wait_time = turnaround - process.cputime - process.io_total
            weighted = turnaround / process.cputime if process.cputime else 0
            rows.append(
                {
                    "name": process.name,
                    "arrival": process.arrival_time,
                    "finish": process.finish_time,
                    "cpu": process.cputime,
                    "io": process.io_total,
                    "turnaround": turnaround,
                    "wait": wait_time,
                    "weighted": round(weighted, 2),
                }
            )
        count = len(rows)
        return {
            "rows": rows,
            "completed": count,
            "average_turnaround": round(
                sum(row["turnaround"] for row in rows) / count, 2
            )
            if count
            else 0,
            "average_wait": round(
                sum(row["wait"] for row in rows) / count, 2
            )
            if count
            else 0,
            "average_weighted": round(
                sum(row["weighted"] for row in rows) / count, 2
            )
            if count
            else 0,
        }

    def export(self, fmt: str) -> tuple[str, str]:
        if fmt == "json":
            return (
                json.dumps(
                    {"snapshot": self.snapshot(), "report": self.report()},
                    ensure_ascii=False,
                    indent=2,
                ),
                "application/json",
            )
        output = io.StringIO()
        rows = self.report()["rows"]
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "name",
                "arrival",
                "finish",
                "cpu",
                "io",
                "turnaround",
                "wait",
                "weighted",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue(), "text/csv"
