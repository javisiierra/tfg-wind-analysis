from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Callable
from uuid import uuid4


@dataclass
class DashboardJob:
    id: str
    status: str
    progress: int
    message: str
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str


class DashboardJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, DashboardJob] = {}
        self._lock = Lock()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, message: str, progress: int = 0) -> str:
        job_id = str(uuid4())
        now = self._now()
        job = DashboardJob(
            id=job_id,
            status="queued",
            progress=progress,
            message=message,
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = self._now()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            data = asdict(job)
        data["job_id"] = data.pop("id")
        return data

    def start_background(self, job_id: str, fn: Callable[..., None], *args: Any) -> None:
        thread = Thread(target=fn, args=(job_id, *args), daemon=True)
        thread.start()
