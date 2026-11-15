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


def _groups(root: Path) -> list[Path]:
    """The process's own folder of cgroup v2 and those above it within the mount, nearest first: a limit
    set on any of them holds for the process. /proc/self/cgroup names the folder ("0::<path>"); where this
    mount has no such folder, its top is the container's own group, as with a cgroup namespace."""
    top = root / "sys/fs/cgroup"
    for line in (_read(root / "proc/self/cgroup") or "").splitlines():
        if line.startswith("0::") and (folder := top / line[3:].lstrip("/")).is_dir():
            return [folder, *(parent for parent in folder.parents if parent == top or top in parent.parents)]
    return [top]


def _memory(root: Path, groups: list[Path]) -> dict:
    """The memory in use, less the cache of files the system drops when it needs the room (the limit
    counts it the same way), and the most the site may take: the least of its groups' limits and the
    machine's memory."""
    group, legacy = groups[0], root / "sys/fs/cgroup/memory"
    machine = _fields(_read(root / "proc/meminfo"))  # in kB
    if (current := _number(_read(group / "memory.current"))) is not None:
        used = current - _fields(_read(group / "memory.stat")).get("inactive_file", 0)
    elif (current := _number(_read(legacy / "memory.usage_in_bytes"))) is not None:
        used = current - _fields(_read(legacy / "memory.stat")).get("total_inactive_file", 0)
    elif {"MemTotal", "MemAvailable"} <= machine.keys():
        used = (machine["MemTotal"] - machine["MemAvailable"]) * 1024
    else:
        return {"used": None, "limit": None, "percent": None}
    # A group with no limit writes "max" (v2), or a number past any machine's memory (v1).
    limits = [_number(_read(folder / "memory.max")) for folder in groups]
    limits += [_number(_read(legacy / "memory.limit_in_bytes")), machine.get("MemTotal", 0) * 1024]
    limit = min((n for n in limits if n), default=None)
    used = max(used, 0)
    return {"used": used, "limit": limit, "percent": _percent(used, limit)}


def _cpu_time(root: Path, groups: list[Path]) -> float | None:
    """The processor time the process's group has taken so far, in seconds."""
    if (usec := _fields(_read(groups[0] / "cpu.stat")).get("usage_usec")) is not None:
        return usec / 1e6
    if (nsec := _number(_read(root / "sys/fs/cgroup/cpuacct/cpuacct.usage"))) is not None:
        return nsec / 1e9
    return None


def _quota(text: str) -> float | None:
    """Processors from "<quota> <period>" in microseconds; none for "max" (v2) or -1 (v1), meaning no quota."""
    quota, _, period = text.partition(" ")
    return int(quota) / int(period) if quota.isdecimal() and period.isdecimal() and int(period) else None


def _cpu_limit(root: Path, groups: list[Path]) -> float:
    """How many processors the process may keep busy at once: the least of its groups' quotas and the
    processors it may run on."""
    legacy = root / "sys/fs/cgroup/cpu"
    quotas = [_quota(_read(folder / "cpu.max") or "") for folder in groups]
    quotas.append(_quota(f"{_read(legacy / 'cpu.cfs_quota_us')} {_read(legacy / 'cpu.cfs_period_us')}"))
    return min([os.process_cpu_count() or 1, *(quota for quota in quotas if quota is not None)])


def _cpu(root: Path, groups: list[Path]) -> dict:
    """How busy the processor is: the group's processor time over CPU_SAMPLE_SECONDS, against its limit."""
    limit, used = _cpu_limit(root, groups), None
    before, started = _cpu_time(root, groups), time.monotonic()
    if before is not None:
        time.sleep(CPU_SAMPLE_SECONDS)
        after = _cpu_time(root, groups)
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
    disk, groups = media_disk(), _groups(root)
    return {
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": _percent(disk.used, disk.used + disk.free),
        },
        "database": {"size": _database_size()},
        "memory": _memory(root, groups),
        "cpu": _cpu(root, groups),
    }
