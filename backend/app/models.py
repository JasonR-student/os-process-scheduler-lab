from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Mode = Literal["simulation", "real"]


class SessionConfig(BaseModel):
    mode: Mode = "simulation"
    continuous: bool = False
    seed: int = 42
    initial_processes: int = Field(default=6, ge=6, le=7)
    time_slice: int = Field(default=1, ge=1, le=10)
    arrival_min: int = Field(default=1, ge=1, le=60)
    arrival_max: int = Field(default=10, ge=1, le=120)
    batch_min: int = Field(default=1, ge=1, le=10)
    batch_max: int = Field(default=3, ge=1, le=20)
    io_probability: int = Field(default=20, ge=0, le=100)
    io_min: int = Field(default=1, ge=1, le=60)
    io_max: int = Field(default=3, ge=1, le=120)
    max_processes: int = Field(default=12, ge=6, le=100)
    tick_ms: int = Field(default=1000, ge=100, le=5000)

    @model_validator(mode="after")
    def validate_ranges(self) -> "SessionConfig":
        if self.arrival_min > self.arrival_max:
            raise ValueError("arrival_min must be <= arrival_max")
        if self.batch_min > self.batch_max:
            raise ValueError("batch_min must be <= batch_max")
        if self.io_min > self.io_max:
            raise ValueError("io_min must be <= io_max")
        if self.initial_processes > self.max_processes:
            raise ValueError("initial_processes must be <= max_processes")
        return self


class ProcessView(BaseModel):
    name: str
    pid: int | None = None
    ppid: int | None = None
    pgid: int | None = None
    state: str
    linux_state: str | None = None
    prio: int
    needtime: int
    cputime: int
    count: int
    arrival_time: int
    io_remain: int
    io_total: int
    finish_time: int
    context_switches: int
    rss_kb: int | None = None
    voluntary_ctxt_switches: int | None = None
    nonvoluntary_ctxt_switches: int | None = None
    fd_count: int | None = None
    started_at: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class SessionEvent(BaseModel):
    type: str
    seq: int
    time: int
    mode: Mode
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    id: str
    mode: Mode
    status: str
    time: int
    created: int
    finished: int
