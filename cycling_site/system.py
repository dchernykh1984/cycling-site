"""What the server has right now: the disk the site keeps its files on, the database, and the memory and
the processor of the container the site runs in. Read at the moment of asking, never stored.

Inside a container the machine's own totals -- /proc/meminfo, the number of processors -- are the
host's. The container's share is its control group's (cgroup v2, else v1); the machine's totals count
only where the group sets no limit, or where there is no group to read.
"""

import os
import shutil
import time
from pathlib import Path

from django.conf import settings
from django.db import connection

#: How long the processor is watched to tell how busy it is: what the system keeps is a running total.
CPU_SAMPLE_SECONDS = 1.0


def media_disk():
    """The disk MEDIA_ROOT is on, measured at its nearest folder that exists yet."""
    path = Path(settings.MEDIA_ROOT)
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path)


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _number(text: str | None) -> int | None:
    return int(text) if text and text.isdecimal() else None


def _fields(text: str | None) -> dict[str, int]:
    """A file of "name value" lines -- memory.stat, cpu.stat, /proc/meminfo -- as numbers by name."""
    rows = (line.split() for line in (text or "").splitlines())
    return {row[0].rstrip(":"): int(row[1]) for row in rows if len(row) > 1 and row[1].isdecimal()}


def _percent(part: float | None, whole: float | None) -> float | None:
    return round(part * 100 / whole, 1) if part is not None and whole else None


def _unified(root: Path) -> Path:
    """The process's own folder of cgroup v2, as /proc/self/cgroup names it ("0::<path>"), where this mount
    has it; else the mount's top, which is the container's own group when it has a cgroup namespace."""
    top = root / "sys/fs/cgroup"
    for line in (_read(root / "proc/self/cgroup") or "").splitlines():
        if line.startswith("0::") and (folder := top / line[3:].lstrip("/")).is_dir():
            return folder
    return top


def _memory(root: Path) -> dict:
    """The memory in use, less the cache of files the system drops when it needs the room (the limit
    counts it the same way), and the most the site may take: its group's limit, never more than the
    machine has."""
    group, legacy = _unified(root), root / "sys/fs/cgroup/memory"
    machine = _fields(_read(root / "proc/meminfo"))  # in kB
    if (current := _number(_read(group / "memory.current"))) is not None:
        used = current - _fields(_read(group / "memory.stat")).get("inactive_file", 0)
        limit = _number(_read(group / "memory.max"))  # "max" when there is none
    elif (current := _number(_read(legacy / "memory.usage_in_bytes"))) is not None:
        used = current - _fields(_read(legacy / "memory.stat")).get("total_inactive_file", 0)
        limit = _number(_read(legacy / "memory.limit_in_bytes"))  # past any machine's memory when there is none
    elif {"MemTotal", "MemAvailable"} <= machine.keys():
        used, limit = (machine["MemTotal"] - machine["MemAvailable"]) * 1024, None
    else:
        return {"used": None, "limit": None, "percent": None}
    total = machine.get("MemTotal", 0) * 1024
    if total and (limit is None or limit > total):
        limit = total
    used = max(used, 0)
    return {"used": used, "limit": limit, "percent": _percent(used, limit)}


def _cpu_time(root: Path) -> float | None:
    """The processor time the group has taken so far, in seconds."""
    if (usec := _fields(_read(_unified(root) / "cpu.stat")).get("usage_usec")) is not None:
        return usec / 1e6
    if (nsec := _number(_read(root / "sys/fs/cgroup/cpuacct/cpuacct.usage"))) is not None:
        return nsec / 1e9
    return None


def _cpu_limit(root: Path) -> float:
    """How many processors the group may keep busy at once: its quota, never more than it may run on."""
    quota, _, period = (_read(_unified(root) / "cpu.max") or "").partition(" ")  # "max 100000" when none
    if not quota.isdecimal():
        legacy = root / "sys/fs/cgroup/cpu"
        quota, period = _read(legacy / "cpu.cfs_quota_us") or "", _read(legacy / "cpu.cfs_period_us") or ""
    machine = os.process_cpu_count() or 1
    if quota.isdecimal() and period.isdecimal() and int(period):  # cgroup v1 writes -1 when there is none
        return min(int(quota) / int(period), machine)
    return machine


def _cpu(root: Path) -> dict:
    """How busy the processor is: the group's processor time over CPU_SAMPLE_SECONDS, against its limit."""
    limit, used = _cpu_limit(root), None
    before, started = _cpu_time(root), time.monotonic()
    if before is not None:
        time.sleep(CPU_SAMPLE_SECONDS)
        after = _cpu_time(root)
        used = None if after is None else (after - before) / (time.monotonic() - started)
    return {
        "used": None if used is None else round(used, 2),
        "limit": round(limit, 2),
        "percent": _percent(used, limit),
    }


def _database_size() -> int | None:
    """What the database takes on its disk, where the database says it."""
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        return cursor.fetchone()[0]


def read(root: Path = Path("/")) -> dict:
    """The server's resources at this moment, in bytes and in processors; what the system does not say is
    None. It takes CPU_SAMPLE_SECONDS, for which the processor is watched.

    The disk's share is counted as ``df`` counts it: the blocks the system keeps for itself are neither
    used nor free, so a full disk reads 100% though they are left.
    """
    disk = media_disk()
    return {
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": _percent(disk.used, disk.used + disk.free),
        },
        "database": {"size": _database_size()},
        "memory": _memory(root),
        "cpu": _cpu(root),
    }
