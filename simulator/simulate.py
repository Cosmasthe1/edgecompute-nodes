"""
EdgeCompute Simulator (Phase 1 reference implementation).

Spins up several in-process, simulated Node Agents (mixing Tier 1 XFRA-style
nodes and Tier 2 volunteer PCs, some deliberately "flaky"), submits a batch
of jobs against a running orchestrator, and reports basic metrics:
Job Completion Time (JCT), success rate, and per-node credit earnings.

This does NOT spawn OS processes — it drives the same NodeAgent class used
by agent/node_agent.py directly in threads, which is enough to exercise the
full poll -> assign -> execute -> report loop against a real FastAPI server
without needing Docker or a network of real machines.

Usage:
    # in one terminal:
    uvicorn orchestrator.main:app --port 8000

    # in another:
    python simulator/simulate.py --nodes 8 --jobs 20
"""
from __future__ import annotations

import argparse
import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from agent.node_agent import NodeAgent  # noqa: E402


def spawn_nodes(base_url: str, count: int) -> list[threading.Thread]:
    threads = []
    for i in range(count):
        is_xfra = i == 0  # first node is a dedicated Tier 1 XFRA node
        agent = NodeAgent(
            base_url=base_url,
            tier=1 if is_xfra else 2,
            cpu=32.0 if is_xfra else random.choice([2.0, 4.0, 8.0]),
            ram=64.0 if is_xfra else random.choice([4.0, 8.0, 16.0]),
            gpu=4 if is_xfra else random.choice([0, 0, 0, 1]),
            region="nairobi-ke",
            poll_interval=random.uniform(1.5, 3.0),
            fail_rate=0.0 if is_xfra else random.uniform(0.0, 0.15),
            flaky=not is_xfra and random.random() < 0.3,
        )
        t = threading.Thread(target=agent.run_forever, daemon=True)
        threads.append(t)
        t.start()
        print(f"[sim] spawned node #{i} tier={agent.tier} cpu={agent.cpu} "
              f"gpu={agent.gpu} flaky={agent.flaky}")
    return threads


def submit_jobs(base_url: str, count: int) -> list[str]:
    client = httpx.Client(timeout=10.0)
    job_ids = []
    for i in range(count):
        req = {
            "payload": f"job-payload-{i}",
            "requirements": {
                "cpu_cores": random.choice([0.5, 1.0, 2.0]),
                "ram_gb": random.choice([1.0, 2.0, 4.0]),
                "gpu_count": random.choice([0, 0, 0, 1]),
                "gpu_vram_gb": random.choice([0.0, 0.0, 8.0]),
            },
            "origin_lat": -1.286389,   # Nairobi
            "origin_lon": 36.817223,
        }
        resp = client.post(f"{base_url}/jobs", json=req)
        resp.raise_for_status()
        job_ids.append(resp.json()["job_id"])
        time.sleep(0.05)
    print(f"[sim] submitted {count} jobs")
    return job_ids


def wait_and_report(base_url: str, job_ids: list[str], timeout_s: float = 60.0) -> None:
    client = httpx.Client(timeout=10.0)
    start = time.time()
    completed: dict[str, dict] = {}

    while time.time() - start < timeout_s and len(completed) < len(job_ids):
        for jid in job_ids:
            if jid in completed:
                continue
            resp = client.get(f"{base_url}/jobs/{jid}")
            if resp.status_code != 200:
                continue
            job = resp.json()
            if job["status"] in ("completed", "failed"):
                completed[jid] = job
        time.sleep(1.0)

    succeeded = [j for j in completed.values() if j["status"] == "completed"]
    failed = [j for j in completed.values() if j["status"] == "failed"]
    unresolved = len(job_ids) - len(completed)

    print("\n=== Simulation Report ===")
    print(f"submitted:   {len(job_ids)}")
    print(f"completed:   {len(succeeded)}")
    print(f"failed:      {len(failed)}")
    print(f"unresolved:  {unresolved} (still queued/assigned when timeout hit)")

    if succeeded:
        jcts = [j["completed_at"] - j["submitted_at"] for j in succeeded]
        print(f"avg JCT:     {sum(jcts)/len(jcts):.2f}s")
        print(f"max JCT:     {max(jcts):.2f}s")

    nodes_resp = client.get(f"{base_url}/nodes")
    nodes = nodes_resp.json()
    print("\n--- Node summary ---")
    for n in nodes:
        print(f"  {n['node_id']}  tier={n['tier']}  online={n['online']}  "
              f"reliability={n['reliability_score']:.2f}  credits={n['credit_balance']:.4f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="EdgeCompute end-to-end simulation")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--nodes", type=int, default=6)
    ap.add_argument("--jobs", type=int, default=15)
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    spawn_nodes(args.url, args.nodes)
    time.sleep(2.0)  # let nodes register before jobs start arriving
    job_ids = submit_jobs(args.url, args.jobs)
    wait_and_report(args.url, job_ids, timeout_s=args.timeout)


if __name__ == "__main__":
    main()
