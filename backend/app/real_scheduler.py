from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import random
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ProcessView, SessionConfig
from .proc_reader import read_process


@dataclass
class RealProcess:
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
    proc: asyncio.subprocess.Process | None = field(default=None, repr=False)

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


class RealSession:
    """A user-space scheduler for child workers created by this session."""

    def __init__(self, config: SessionConfig, session_id: str | None = None):
        self.id = session_id or uuid.uuid4().hex[:12]
        self.config = config
        self.mode = "real"
        self.status = "ready"
        self.now = 0
        self.seq = 0
        self.pid_counter = 0
        self.total_created = 0
        self.context_switches = 0
        self.next_arrival = 0
        self.rng = random.Random(config.seed)
        self.processes: dict[str, RealProcess] = {}
        self.ready: list[str] = []
        self.blocked: list[str] = []
        self.finished: list[str] = []
        self.running: str | None = None
        self.event_history: list[dict[str, Any]] = []
        self.gantt: list[dict[str, Any]] = []
        self.priority_history: dict[str, list[dict[str, int]]] = {}
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.runner_task: asyncio.Task[None] | None = None
        self.error: str | None = None
        self.worker_path = self._find_worker()
        self._reset_state()

    def _find_worker(self) -> Path:
        root = Path(__file__).resolve().parents[2]
        candidates = (
            root / "native" / "scheduler-worker",
            root / "native" / "bin" / "scheduler-worker",
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _reset_state(self) -> None:
        self.now = 0
        self.seq = 0
        self.pid_counter = 0
        self.total_created = 0
        self.context_switches = 0
        self.next_arrival = self.rng.randint(
            self.config.arrival_min, self.config.arrival_max
        )
        self.processes.clear()
        self.ready.clear()
        self.blocked.clear()
        self.finished.clear()
        self.running = None
        self.event_history.clear()
        self.gantt.clear()
        self.priority_history.clear()
        self.status = "ready"
        self.error = None

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

    async def _sample(self, process: RealProcess) -> None:
        if process.pid is None:
            return
        stats = read_process(process.pid)
        for key, value in stats.items():
            if hasattr(process, key):
                setattr(process, key, value)
        self._record_event("proc_sample", {"process": process.view()})

    async def _spawn_worker(self, arrival_time: int) -> RealProcess | None:
        if self.total_created >= self.config.max_processes:
            return None
        if not self.worker_path.exists():
            self.error = (
                f"worker not found: {self.worker_path}. "
                "Build native/scheduler-worker on Linux first."
            )
            self.status = "error"
            self._record_event("error", {"message": self.error})
            return None

        self.pid_counter += 1
        name = f"P{self.pid_counter}"
        needtime = self.rng.randint(1, 20)
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.worker_path),
                "--name",
                name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            self.error = f"cannot start native worker: {exc}"
            self.status = "error"
            self._record_event("error", {"message": self.error})
            return None
        process = RealProcess(
            name=name,
            needtime=needtime,
            arrival_time=arrival_time,
            prio=50 - needtime,
            pid=proc.pid,
            pgid=proc.pid,
            proc=proc,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        if proc.stdout is not None:
            ready_line = await proc.stdout.readline()
            if not ready_line.startswith(b"READY"):
                await self._terminate_process(process)
                self.error = f"worker {name} failed to initialize"
                self.status = "error"
                self._record_event("error", {"message": self.error})
                return None
        process.history.append(
            {"time": arrival_time, "state": "W", "reason": "created"}
        )
        self.processes[name] = process
        self.ready.append(name)
        self.priority_history[name] = [{"time": arrival_time, "prio": process.prio}]
        self.total_created += 1
        await self._sample(process)
        self._record_event(
            "process_created",
            {"process": process.view(), "reason": "arrival"},
        )
        self._stop_process(process)
        return process

    async def _terminate_process(self, process: RealProcess) -> None:
        if process.proc is None or process.proc.returncode is not None:
            return
        try:
            if process.pgid:
                os.killpg(process.pgid, signal.SIGTERM)
            await asyncio.wait_for(process.proc.wait(), timeout=0.5)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                if process.pgid:
                    os.killpg(process.pgid, signal.SIGKILL)
                await process.proc.wait()
            except ProcessLookupError:
                pass

    def _stop_process(self, process: RealProcess) -> None:
        if process.pid:
            try:
                os.kill(process.pid, signal.SIGSTOP)
            except ProcessLookupError:
                pass

    def _continue_process(self, process: RealProcess) -> None:
        if process.pid:
            try:
                os.kill(process.pid, signal.SIGCONT)
            except ProcessLookupError:
                pass

    async def _send_command(
        self, process: RealProcess, command: str, expected: tuple[bytes, ...]
    ) -> bytes:
        if process.proc is None or process.proc.stdin is None:
            raise RuntimeError(f"worker {process.name} has no control pipe")
        self._continue_process(process)
        process.proc.stdin.write(command.encode())
        await process.proc.stdin.drain()
        if process.proc.stdout is None:
            raise RuntimeError(f"worker {process.name} has no output pipe")
        while True:
            line = await process.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"worker {process.name} exited unexpectedly")
            if line.startswith(expected):
                return line

    async def _wake_process(self, process: RealProcess) -> None:
        line = await self._send_command(process, "RESUME\n", (b"IO_RESUMED",))
        if line.startswith(b"IO_RESUMED"):
            self._stop_process(process)
            process.state = "W"
            process.io_remain = 0
            process.history.append(
                {"time": self.now, "state": "W", "reason": "io-complete"}
            )
            self.ready.append(process.name)
            await self._sample(process)
            self._record_event(
                "process_woken",
                {"process": process.view(), "reason": "io-complete"},
            )

    async def _run_process(self, process: RealProcess) -> None:
        action = "READY"
        if process.needtime <= self.config.time_slice:
            action = "FINISH"
        elif self.rng.randrange(100) < self.config.io_probability:
            action = "IO"
            process.io_remain = self.rng.randint(
                self.config.io_min, self.config.io_max
            )
            process.io_total += process.io_remain

        cpu_ms = max(100, min(800, self.config.tick_ms - 100))
        line = await self._send_command(
            process,
            f"RUN {cpu_ms} {action} {process.io_remain}\n",
            (b"CPU_SLICE_DONE", b"IO_REQUEST", b"FINISHED"),
        )
        process.cputime += self.config.time_slice
        process.needtime -= self.config.time_slice
        process.count += 1
        process.context_switches += 1
        self.context_switches += 1
        self._record_event(
            "context_switch",
            {
                "process": process.view(),
                "reason": "user-space SIGSTOP/SIGCONT",
            },
        )
        self.gantt.append(
            {"time": self.now, "process": process.name, "state": "R", "reason": action}
        )
        self.running = None

        if line.startswith(b"FINISHED"):
            process.needtime = 0
            process.state = "F"
            process.finish_time = self.now
            process.history.append(
                {"time": self.now, "state": "F", "reason": "needtime-zero"}
            )
            self.finished.append(process.name)
            await process.proc.wait() if process.proc else None
            await self._sample(process)
            self._record_event(
                "process_finished",
                {"process": process.view(), "reason": "needtime-zero"},
            )
        elif line.startswith(b"IO_REQUEST"):
            process.state = "B"
            process.history.append(
                {"time": self.now, "state": "B", "reason": "io-request"}
            )
            self.blocked.append(process.name)
            self._stop_process(process)
            await self._sample(process)
            self._record_event(
                "process_blocked",
                {"process": process.view(), "reason": "io-request"},
            )
        else:
            process.state = "W"
            process.prio -= 3
            process.history.append(
                {"time": self.now, "state": "W", "reason": "preempted"}
            )
            self.ready.append(process.name)
            self._stop_process(process)
            await self._sample(process)
            self._record_event(
                "process_preempted",
                {"process": process.view(), "reason": "time-slice-end"},
            )

        self.priority_history.setdefault(process.name, []).append(
            {"time": self.now, "prio": process.prio}
        )

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
        process.history.append(
            {"time": self.now, "state": "R", "reason": "dispatch"}
        )
        self.running = name
        self._record_event(
            "process_scheduled",
            {"process": process.view(), "reason": "highest-priority-ready"},
        )

    async def step(self) -> dict[str, Any]:
        if self.status in {"stopped", "completed", "error"}:
            return self.snapshot()
        if not self.processes:
            for _ in range(self.config.initial_processes):
                await self._spawn_worker(0)
            self._schedule_next()
        if self.status == "error":
            return self.snapshot()
        was_playing = self.status == "running"
        self.status = "running"
        self.now += self.config.time_slice

        for name in list(self.blocked):
            process = self.processes[name]
            process.io_remain -= self.config.time_slice
            if process.io_remain <= 0:
                self.blocked.remove(name)
                await self._wake_process(process)

        if self.running is not None:
            try:
                await self._run_process(self.processes[self.running])
            except (OSError, RuntimeError) as exc:
                self.error = f"worker control failed: {exc}"
                self.status = "error"
                self._record_event("error", {"message": self.error})
                for process in self.processes.values():
                    await self._terminate_process(process)
                self.running = None
                return self.snapshot()

        for name in self.ready:
            process = self.processes[name]
            process.prio += 1
            self.priority_history[name].append(
                {"time": self.now, "prio": process.prio}
            )

        if (
            self.total_created < self.config.max_processes
            and self.now >= self.next_arrival
        ):
            count = min(
                self.rng.randint(self.config.batch_min, self.config.batch_max),
                self.config.max_processes - self.total_created,
            )
            for _ in range(count):
                await self._spawn_worker(self.now)
            self.next_arrival = self.now + self.rng.randint(
                self.config.arrival_min, self.config.arrival_max
            )

        self._schedule_next()
        if (
            self.total_created >= self.config.max_processes
            and not self.ready
            and not self.blocked
            and self.running is None
        ):
            self.status = "completed"
            self._record_event(
                "report_ready", {"message": "All real workers finished"}
            )
        elif not was_playing:
            self.status = "paused"
        self._record_event("snapshot", self.snapshot())
        return self.snapshot()

    async def play(self) -> None:
        while self.status == "running":
            await self.step()
            await asyncio.sleep(self.config.tick_ms / 1000)

    async def start(self) -> dict[str, Any]:
        if not self.processes:
            for _ in range(self.config.initial_processes):
                await self._spawn_worker(0)
            self._schedule_next()
        if self.status == "error":
            return self.snapshot()
        self.status = "running"
        if self.runner_task is None or self.runner_task.done():
            self.runner_task = asyncio.create_task(self.play())
        self._record_event("session_started", {"message": "Real playback started"})
        return self.snapshot()

    async def pause(self) -> dict[str, Any]:
        self.status = "paused"
        for process in self.processes.values():
            if process.state != "F":
                self._stop_process(process)
        self._record_event("session_paused", {"message": "Real playback paused"})
        return self.snapshot()

    async def reset(self) -> dict[str, Any]:
        if self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()
        for process in self.processes.values():
            await self._terminate_process(process)
        self.rng = random.Random(self.config.seed)
        self._reset_state()
        self._record_event("session_reset", {"message": "Real session reset"})
        return self.snapshot()

    async def stop(self) -> dict[str, Any]:
        self.status = "stopped"
        if self.runner_task and not self.runner_task.done():
            self.runner_task.cancel()
        for process in self.processes.values():
            await self._terminate_process(process)
        self.running = None
        self._record_event("session_stopped", {"message": "Real session stopped"})
        return self.snapshot()

    async def back(self) -> dict[str, Any]:
        self.error = "真实 PID 模式不支持回退；只能查看已经产生的事件历史。"
        self._record_event("error", {"message": self.error})
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "status": self.status,
            "time": self.now,
            "mode": self.mode,
            "next_arrival": self.next_arrival,
            "created": self.total_created,
            "context_switches": self.context_switches,
            "cpu_utilization": 100 if self.running else 0,
            "running": self.processes[self.running].view()
            if self.running
            else None,
            "ready": [self.processes[name].view() for name in self.ready],
            "blocked": [self.processes[name].view() for name in self.blocked],
            "finished": [self.processes[name].view() for name in self.finished],
            "processes": [process.view() for process in self.processes.values()],
            "events": self.event_history[-40:],
            "gantt": self.gantt[-120:],
            "priority_history": self.priority_history,
            "error": self.error,
        }

    def report(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for name in self.finished:
            process = self.processes[name]
            turnaround = process.finish_time - process.arrival_time
            wait_time = turnaround - process.cputime - process.io_total
            rows.append(
                {
                    "name": process.name,
                    "pid": process.pid,
                    "arrival": process.arrival_time,
                    "finish": process.finish_time,
                    "cpu": process.cputime,
                    "io": process.io_total,
                    "turnaround": turnaround,
                    "wait": wait_time,
                    "weighted": round(
                        turnaround / process.cputime if process.cputime else 0, 2
                    ),
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
                "pid",
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
