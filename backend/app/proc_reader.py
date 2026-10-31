from __future__ import annotations

import os
from pathlib import Path


def read_process(pid: int) -> dict[str, int | str | None]:
    """Read a small, portable subset of /proc for a process we own."""
    root = Path("/proc") / str(pid)
    result: dict[str, int | str | None] = {
        "pid": pid,
        "ppid": None,
        "pgid": None,
        "linux_state": None,
        "rss_kb": None,
        "voluntary_ctxt_switches": None,
        "nonvoluntary_ctxt_switches": None,
        "fd_count": None,
    }
    try:
        stat_fields = (root / "stat").read_text().split()
        result["linux_state"] = stat_fields[2]
        result["ppid"] = int(stat_fields[3])
        result["pgid"] = int(stat_fields[4])

        for line in (root / "status").read_text().splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            if key == "VmRSS":
                result["rss_kb"] = int(value.split()[0])
            elif key == "voluntary_ctxt_switches":
                result["voluntary_ctxt_switches"] = int(value)
            elif key == "nonvoluntary_ctxt_switches":
                result["nonvoluntary_ctxt_switches"] = int(value)

        result["fd_count"] = len(list((root / "fd").iterdir()))
    except (FileNotFoundError, PermissionError, IndexError, ValueError):
        result["linux_state"] = None
    return result


def process_exists(pid: int | None) -> bool:
    return bool(pid and os.path.exists(f"/proc/{pid}"))
