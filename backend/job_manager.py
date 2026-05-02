"""
JobManager — In-memory per-job state with SSE log queues.

Architecture decision: queue.Queue (thread-safe) bridges the synchronous
pipeline_runner thread and the async FastAPI SSE generator.
Sentinel value None signals stream termination.
"""
from __future__ import annotations

import queue
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"              # pending | running | done | error
    log_queue: queue.Queue = field(default_factory=queue.Queue)
    files: dict[str, str] = field(default_factory=dict)
    zip_path: Optional[str] = None
    error: Optional[str] = None
    discovered_urls: list[str] = field(default_factory=list)


class JobManager:
    """Singleton store for active pipeline jobs.

    Thread-safety: dict operations in CPython are GIL-protected for
    simple get/set; sufficient for single-user internal tool.
    For multi-user: replace with Redis-backed store.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self) -> Job:
        job = Job()
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def push_log(self, job_id: str, msg: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.log_queue.put(msg)

    def finish(self, job_id: str, result: dict) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.files = result.get("files", {})
        job.zip_path = result.get("zip_path")
        job.error = result.get("error")
        job.status = "error" if result.get("error") else "done"
        job.log_queue.put(None)  # SSE sentinel — terminates stream

    def finish_discovery(self, job_id: str, result: dict) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.discovered_urls = result.get("urls", [])
        job.error = result.get("error")
        job.status = "error" if result.get("error") else "done"
        job.log_queue.put(None)


# Module-level singleton — imported by api.py
job_manager = JobManager()
