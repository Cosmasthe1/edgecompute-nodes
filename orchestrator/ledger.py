"""
Credit-based incentive ledger (replaces real cryptocurrency/fiat payments —
see the architecture reconciliation notes for why).

Providers earn credits when a job they ran completes successfully. The
payout weights resource type (GPU > RAM > CPU), how long the job ran, and
the node's current EWMA reliability score, so flaky nodes earn less for
the same work.
"""
from __future__ import annotations

from .models import ResourceProfile

# relative value per unit, per second of job runtime
RATE_PER_GPU_SECOND = 0.02
RATE_PER_CPU_CORE_SECOND = 0.0015
RATE_PER_GB_RAM_SECOND = 0.0005


def compute_payout(requirements: ResourceProfile, runtime_seconds: float, reliability_score: float) -> float:
    """Credits earned for successfully completing one job."""
    base = (
        requirements.gpu_count * RATE_PER_GPU_SECOND
        + requirements.cpu_cores * RATE_PER_CPU_CORE_SECOND
        + requirements.ram_gb * RATE_PER_GB_RAM_SECOND
    ) * max(runtime_seconds, 0.0)

    # reliability acts as a multiplier: a flaky node earns less for the
    # same nominal work, which nudges the incentive toward consistency
    return base * max(0.1, reliability_score)
