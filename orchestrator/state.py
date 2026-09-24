"""
In-memory state store for the orchestrator.

The project proposal calls for Redis-backed distributed state (see
README). This module isolates all state access behind a small interface
so swapping in a real Redis-backed job queue later is a localized change,
not a rewrite: every other module only calls into `STORE`, never touches
dicts directly.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .models import Job, JobStatus, Node

STALE_NODE_TIMEOUT_SECONDS = 20.0  # miss this many seconds of polling -> considered offline


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.nodes: dict[str, Node] = {}
        self.jobs: dict[str, Job] = {}
        self.queue: list[str] = []  # job_ids waiting for assignment, FIFO

    # --- nodes -------------------------------------------------------
    def register_node(self, node: Node) -> None:
        with self._lock:
            self.nodes[node.node_id] = node

    def touch_node(self, node_id: str) -> Optional[Node]:
        with self._lock:
            node = self.nodes.get(node_id)
            if node:
                node.last_seen = time.time()
            return node

    def active_nodes(self) -> list[Node]:
        cutoff = time.time() - STALE_NODE_TIMEOUT_SECONDS
        with self._lock:
            return [n for n in self.nodes.values() if n.last_seen >= cutoff]

    def stale_nodes(self) -> list[Node]:
        cutoff = time.time() - STALE_NODE_TIMEOUT_SECONDS
        with self._lock:
            return [n for n in self.nodes.values() if n.last_seen < cutoff]

    # --- jobs ----------------------------------------------------------
    def submit_job(self, job: Job) -> None:
        with self._lock:
            self.jobs[job.job_id] = job
            self.queue.append(job.job_id)

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self.jobs.get(job_id)

    def pop_next_assignable(self) -> Optional[Job]:
        """Pop the oldest still-queued job, if any (simple FIFO priority)."""
        with self._lock:
            for i, job_id in enumerate(self.queue):
                job = self.jobs[job_id]
                if job.status == JobStatus.QUEUED:
                    del self.queue[i]
                    return job
            return None

    def requeue(self, job: Job) -> None:
        with self._lock:
            job.status = JobStatus.QUEUED
            job.assigned_node_id = None
            self.queue.insert(0, job.job_id)  # priority re-entry


STORE = Store()
