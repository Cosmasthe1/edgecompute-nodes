"""
Scheduling strategies for matching queued jobs to available nodes.

All strategies score candidate nodes; the lowest-cost node wins. The
default ("hybrid") strategy implements the pseudo-cost function from the
project proposal:

    Cost(job, node) = ComputingCost + CommunicationCost
                       + ReliabilityCost + EnergyCost

ComputingCost uses the convex "Cloud Morphing" utilization function so the
scheduler naturally spreads load toward ~50% utilization per node instead
of packing one node to 100% while others sit idle.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

from .models import Job, Node, ResourceProfile


def fits(node: Node, req: ResourceProfile) -> bool:
    """Hard capability filter — does this node even have the resources?"""
    return (
        node.resources.cpu_cores >= req.cpu_cores
        and node.resources.ram_gb >= req.ram_gb
        and node.resources.gpu_count >= req.gpu_count
        and node.resources.gpu_vram_gb >= req.gpu_vram_gb
    )


def _utilization_after(node: Node, req: ResourceProfile) -> float:
    """Approximate CPU-core utilization if this job were assigned here."""
    if node.resources.cpu_cores <= 0:
        return 1.0
    rho = req.cpu_cores / node.resources.cpu_cores
    return min(rho, 0.999)  # keep strictly < 1 to avoid division by zero


def _convex_utilization_cost(rho: float) -> float:
    """f(rho) = ((2*rho - 1)^2 / (1 - rho)) + 1  — minimized at rho = 0.5."""
    rho = min(max(rho, 0.0), 0.999)
    return ((2 * rho - 1) ** 2) / (1 - rho) + 1


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 500.0  # unknown distance -> assume moderately far
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def computing_cost(node: Node, req: ResourceProfile) -> float:
    rho = _utilization_after(node, req)
    return _convex_utilization_cost(rho)


def communication_cost(node: Node, job: Job) -> float:
    dist_km = _haversine_km(node.lat, node.lon, job.origin_lat, job.origin_lon)
    return dist_km / 100.0  # normalize: 100km ~= 1 cost unit


def reliability_cost(node: Node) -> float:
    # invert reliability_score (0..1, higher is better) into a cost
    return (1.0 - node.reliability_score) * 3.0


def energy_cost(node: Node, req: ResourceProfile) -> float:
    # crude proxy: GPU jobs draw more power than CPU-only jobs
    estimated_kw = 0.05 + req.gpu_count * 0.3 + req.cpu_cores * 0.01
    return estimated_kw * node.energy_cost_per_kwh


def hybrid_cost(node: Node, job: Job) -> float:
    return (
        computing_cost(node, job.requirements)
        + communication_cost(node, job)
        + reliability_cost(node)
        + energy_cost(node, job.requirements)
    )


def greedy_cost(node: Node, job: Job) -> float:
    """Least-loaded-first: ignore everything except current utilization."""
    return _utilization_after(node, job.requirements)


def geographic_cost(node: Node, job: Job) -> float:
    """Nearest node wins, full stop."""
    return communication_cost(node, job)


def power_aware_cost(node: Node, job: Job) -> float:
    """Prioritize nodes with power/utilization headroom."""
    return computing_cost(node, job.requirements) + energy_cost(node, job.requirements) * 2


STRATEGIES: dict[str, Callable[[Node, Job], float]] = {
    "greedy": greedy_cost,
    "geographic": geographic_cost,
    "power_aware": power_aware_cost,
    "hybrid": hybrid_cost,
    # "rl" is a documented stretch goal — see README; not implemented here.
}


def select_node(job: Job, candidate_nodes: list[Node], strategy: str = "hybrid") -> Optional[Node]:
    """Pick the lowest-cost node that can actually fit the job."""
    cost_fn = STRATEGIES.get(strategy, hybrid_cost)
    eligible = [n for n in candidate_nodes if fits(n, job.requirements) and n.current_job_id is None]
    if not eligible:
        return None
    return min(eligible, key=lambda n: cost_fn(n, job))
