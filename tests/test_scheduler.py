"""
Tests for orchestrator.scheduler: capability filtering and each scheduling
strategy (greedy, geographic, power_aware, hybrid).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from orchestrator.models import Job, Node, ResourceProfile, Tier  # noqa: E402
from orchestrator.scheduler import (  # noqa: E402
    STRATEGIES,
    _convex_utilization_cost,
    _haversine_km,
    energy_cost,
    fits,
    reliability_cost,
    select_node,
)


def make_node(**overrides) -> Node:
    defaults = dict(
        tier=Tier.VOLUNTEER,
        resources=ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=0, gpu_vram_gb=0),
        region="nairobi-ke",
        lat=-1.28, lon=36.82,
        reliability_score=0.8,
    )
    defaults.update(overrides)
    return Node(**defaults)


def make_job(**overrides) -> Job:
    defaults = dict(
        payload="p",
        requirements=ResourceProfile(cpu_cores=1, ram_gb=1, gpu_count=0, gpu_vram_gb=0),
        origin_lat=-1.28, origin_lon=36.82,
    )
    defaults.update(overrides)
    return Job(**defaults)


# --- fits() ----------------------------------------------------------------

def test_fits_true_when_node_has_enough_resources():
    node = make_node(resources=ResourceProfile(cpu_cores=8, ram_gb=16, gpu_count=1, gpu_vram_gb=24))
    req = ResourceProfile(cpu_cores=2, ram_gb=4, gpu_count=1, gpu_vram_gb=16)
    assert fits(node, req) is True


@pytest.mark.parametrize("field,value", [
    ("cpu_cores", 100), ("ram_gb", 1000), ("gpu_count", 10), ("gpu_vram_gb", 1000),
])
def test_fits_false_when_any_single_requirement_exceeds_capacity(field, value):
    node = make_node(resources=ResourceProfile(cpu_cores=4, ram_gb=8, gpu_count=1, gpu_vram_gb=24))
    req_kwargs = dict(cpu_cores=1, ram_gb=1, gpu_count=0, gpu_vram_gb=0)
    req_kwargs[field] = value
    assert fits(node, ResourceProfile(**req_kwargs)) is False


# --- select_node() -----------------------------------------------------

def test_select_node_returns_none_when_no_node_fits():
    node = make_node(resources=ResourceProfile(cpu_cores=1, ram_gb=1))
    job = make_job(requirements=ResourceProfile(cpu_cores=64, ram_gb=64))
    assert select_node(job, [node]) is None


def test_select_node_returns_none_when_pool_is_empty():
    job = make_job()
    assert select_node(job, []) is None


def test_select_node_skips_nodes_already_running_a_job():
    busy = make_node(current_job_id="some-other-job")
    idle = make_node()
    job = make_job()
    chosen = select_node(job, [busy, idle], strategy="greedy")
    assert chosen is not None
    assert chosen.node_id == idle.node_id


@pytest.mark.parametrize("strategy", list(STRATEGIES.keys()))
def test_every_strategy_picks_an_eligible_node_when_one_exists(strategy):
    node = make_node()
    job = make_job()
    chosen = select_node(job, [node], strategy=strategy)
    assert chosen is not None
    assert chosen.node_id == node.node_id


def test_unknown_strategy_falls_back_to_hybrid():
    node = make_node()
    job = make_job()
    chosen_default = select_node(job, [node], strategy="not-a-real-strategy")
    chosen_hybrid = select_node(job, [node], strategy="hybrid")
    assert chosen_default is not None
    assert chosen_default.node_id == chosen_hybrid.node_id


def test_geographic_strategy_prefers_the_nearer_node():
    near = make_node(lat=-1.28, lon=36.82)   # same as job origin
    far = make_node(lat=40.0, lon=-74.0)     # New York, far from Nairobi
    job = make_job(origin_lat=-1.28, origin_lon=36.82)
    chosen = select_node(job, [near, far], strategy="geographic")
    assert chosen.node_id == near.node_id


def test_greedy_strategy_prefers_least_loaded_node():
    small_capacity = make_node(resources=ResourceProfile(cpu_cores=1.1, ram_gb=8))   # job uses ~91% of it
    large_capacity = make_node(resources=ResourceProfile(cpu_cores=32, ram_gb=8))     # job uses ~3% of it
    job = make_job(requirements=ResourceProfile(cpu_cores=1, ram_gb=1))
    chosen = select_node(job, [small_capacity, large_capacity], strategy="greedy")
    assert chosen.node_id == large_capacity.node_id


def test_hybrid_strategy_prefers_more_reliable_node_when_otherwise_equal():
    unreliable = make_node(reliability_score=0.1)
    reliable = make_node(reliability_score=0.95)
    job = make_job()
    chosen = select_node(job, [unreliable, reliable], strategy="hybrid")
    assert chosen.node_id == reliable.node_id


# --- cost function components -------------------------------------------

def test_convex_utilization_cost_minimized_near_half_utilization():
    cost_at_half = _convex_utilization_cost(0.5)
    cost_at_low = _convex_utilization_cost(0.05)
    cost_at_high = _convex_utilization_cost(0.95)
    assert cost_at_half < cost_at_low
    assert cost_at_half < cost_at_high


def test_convex_utilization_cost_grows_rapidly_past_0_75():
    cost_at_75 = _convex_utilization_cost(0.75)
    cost_at_90 = _convex_utilization_cost(0.90)
    assert cost_at_90 > cost_at_75 * 2


def test_haversine_returns_zero_for_identical_points():
    assert _haversine_km(-1.28, 36.82, -1.28, 36.82) == pytest.approx(0.0, abs=1e-6)


def test_haversine_handles_missing_coordinates_gracefully():
    # should not raise; falls back to an assumed distance rather than crashing
    dist = _haversine_km(None, None, -1.28, 36.82)
    assert dist > 0


def test_reliability_cost_is_lower_for_more_reliable_node():
    reliable = make_node(reliability_score=0.9)
    unreliable = make_node(reliability_score=0.1)
    assert reliability_cost(reliable) < reliability_cost(unreliable)


def test_energy_cost_increases_with_gpu_requirement():
    node = make_node()
    cpu_only = ResourceProfile(cpu_cores=1, ram_gb=1, gpu_count=0)
    with_gpu = ResourceProfile(cpu_cores=1, ram_gb=1, gpu_count=2)
    assert energy_cost(node, with_gpu) > energy_cost(node, cpu_only)
