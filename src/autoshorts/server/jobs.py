"""In-process job registry + progress event streaming.

A 'job' is one invocation of the shorts pipeline. Jobs are long-running so the
HTTP request that starts one returns immediately with a run_id; the client
subscribes to Server-Sent Events at /api/runs/{run_id}/progress to follow
stages and finish.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["pending", "running", "done", "failed", "cancelled"]


@dataclass
class ProgressEvent:
    ts: float
    stage: str
    message: str
    progress: float   # 0..1


@dataclass
class Job:
    id: str
    run_folder: str                      # e.g. "2026-04-20_15-30-00"
    source: str                          # URL or file path
    status: JobStatus = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    events: list[ProgressEvent] = field(default_factory=list)
    result: dict[str, Any] | None = None
    _listeners: list[asyncio.Queue] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def publish(self, event: ProgressEvent) -> None:
        """Append an event and fan it out to any SSE listeners. Thread-safe
        because the pipeline runs in a worker thread."""
        with self._lock:
            self.events.append(event)
            listeners = list(self._listeners)
        for q in listeners:
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            # Replay buffered events so a late subscriber doesn't miss stages.
            for e in self.events:
                try:
                    q.put_nowait(e)
                except Exception:
                    break
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    def mark_running(self) -> None:
        self.status = "running"
        self.started_at = time.time()

    def mark_done(self, result: dict[str, Any]) -> None:
        self.status = "done"
        self.finished_at = time.time()
        self.result = result

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.finished_at = time.time()
        self.error = error


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, source: str, run_folder: str) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(id=jid, run_folder=run_folder, source=source)
        with self._lock:
            self._jobs[jid] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def by_run_folder(self, run_folder: str) -> Job | None:
        with self._lock:
            for j in self._jobs.values():
                if j.run_folder == run_folder:
                    return j
        return None

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)


REGISTRY = JobRegistry()
