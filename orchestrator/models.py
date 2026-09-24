"""
Shared data models for the EdgeCompute orchestrator.

Tier 1 = dedicated XFRA-style GPU nodes (reliable, managed).
Tier 2 = volunteer PCs (unreliable, variable availability).
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Tier(int, Enum):
    XFRA = 1       # dedicated GPU node
    VOLUNTEER = 2  # idle personal computer


class JobStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Node registration / polling
# ---------------------------------------------------------------------------

class ResourceProfile(BaseModel):
    cpu_cores: float
    ram_gb: float
    gpu_count: int = 0
    gpu_vram_gb: float = 0.0


class NodeRegisterRequest(BaseModel):
    tier: Tier
    resources: ResourceProfile
    region: str = Field(description="Coarse location label, e.g. 'nairobi-ke'")
    # crude lat/lon for CommunicationCost; optional
    lat: Optional[float] = None
    lon: Optional[float] = None
    energy_cost_per_kwh: float = 0.15  # USD/kWh, used for EnergyCost


class NodeRegisterResponse(BaseModel):
    node_id: str
    poll_interval_seconds: float = 5.0


class JobResult(BaseModel):
    job_id: str
    success: bool
    latency_ms: float
    output: Optional[str] = None
    error: Optional[str] = None


class PollRequest(BaseModel):
    """Sent by a Node Agent on every poll cycle."""
    available_resources: ResourceProfile
    completed_results: list[JobResult] = Field(default_factory=list)


class AssignedJob(BaseModel):
    job_id: str
    payload: str
    requirements: ResourceProfile


class PollResponse(BaseModel):
    assigned_job: Optional[AssignedJob] = None
    credit_balance: float = 0.0


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------

class JobSubmitRequest(BaseModel):
    payload: str
    requirements: ResourceProfile
    # optional origin for CommunicationCost; falls back to orchestrator region
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None


class JobSubmitResponse(BaseModel):
    job_id: str
    status: JobStatus


# ---------------------------------------------------------------------------
# Internal server-side records (not exposed directly over the wire)
# ---------------------------------------------------------------------------

class Node(BaseModel):
    node_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    tier: Tier
    resources: ResourceProfile
    region: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    energy_cost_per_kwh: float = 0.15

    last_seen: float = Field(default_factory=time.time)
    reliability_score: float = 0.8  # EWMA, starts optimistic-but-cautious
    credit_balance: float = 0.0

    # current job assignment, if any
    current_job_id: Optional[str] = None


class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    payload: str
    requirements: ResourceProfile
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None

    status: JobStatus = JobStatus.QUEUED
    assigned_node_id: Optional[str] = None
    submitted_at: float = Field(default_factory=time.time)
    assigned_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[JobResult] = None
