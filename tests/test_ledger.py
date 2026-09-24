"""
Tests for orchestrator.ledger: credit payout scaling with resource type,
runtime, and reliability.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from orchestrator.ledger import compute_payout  # noqa: E402
from orchestrator.models import ResourceProfile  # noqa: E402


def test_payout_is_zero_for_zero_runtime():
    req = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=1)
    assert compute_payout(req, runtime_seconds=0, reliability_score=1.0) == 0.0


def test_payout_scales_linearly_with_runtime():
    req = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=0)
    short = compute_payout(req, runtime_seconds=10, reliability_score=1.0)
    long = compute_payout(req, runtime_seconds=20, reliability_score=1.0)
    assert long == pytest.approx(short * 2, rel=1e-6)


def test_gpu_jobs_pay_more_than_equivalent_cpu_only_jobs():
    cpu_only = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=0)
    with_gpu = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=1)
    payout_cpu = compute_payout(cpu_only, runtime_seconds=10, reliability_score=1.0)
    payout_gpu = compute_payout(with_gpu, runtime_seconds=10, reliability_score=1.0)
    assert payout_gpu > payout_cpu


def test_payout_increases_with_cpu_cores_and_ram():
    small = ResourceProfile(cpu_cores=1, ram_gb=1)
    large = ResourceProfile(cpu_cores=8, ram_gb=32)
    payout_small = compute_payout(small, runtime_seconds=10, reliability_score=1.0)
    payout_large = compute_payout(large, runtime_seconds=10, reliability_score=1.0)
    assert payout_large > payout_small


def test_lower_reliability_reduces_payout_for_identical_work():
    req = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=1)
    reliable = compute_payout(req, runtime_seconds=10, reliability_score=0.9)
    unreliable = compute_payout(req, runtime_seconds=10, reliability_score=0.2)
    assert reliable > unreliable


def test_reliability_multiplier_has_a_floor_so_payout_never_hits_zero():
    req = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=1)
    payout = compute_payout(req, runtime_seconds=10, reliability_score=0.0)
    assert payout > 0.0


def test_negative_runtime_does_not_produce_negative_payout():
    req = ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=1)
    payout = compute_payout(req, runtime_seconds=-5, reliability_score=1.0)
    assert payout == 0.0
