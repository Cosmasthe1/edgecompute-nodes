"""
EdgeCompute Node Agent.

Pull-based by design: this agent NEVER listens on an inbound port. It
registers once, then repeatedly polls the orchestrator's /poll endpoint
on an interval, reporting availability and picking up any assigned job
in the response. This is what makes it safe to run behind a home
router/NAT with zero port forwarding.

Run with:
    python agent/node_agent.py --url http://localhost:8000 --tier 2 \
        --cpu 8 --ram 16 --gpu 0

A real deployment would execute `assigned_job.payload` inside a Docker
container (see README "Phase 3"); this reference implementation simulates
job execution with a short sleep so the full poll/assign/report loop can
be exercised end-to-end without a container runtime.
"""
from __future__ import annotations

import argparse
import logging
import random
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [agent] %(message)s")
log = logging.getLogger("edgecompute.agent")


class NodeAgent:
    def __init__(self, base_url: str, tier: int, cpu: float, ram: float, gpu: int,
                 region: str, poll_interval: float, fail_rate: float = 0.0,
                 flaky: bool = False):
        self.base_url = base_url.rstrip("/")
        self.tier = tier
        self.cpu = cpu
        self.ram = ram
        self.gpu = gpu
        self.region = region
        self.poll_interval = poll_interval
        self.fail_rate = fail_rate   # simulate jobs failing, for churn/testing
        self.flaky = flaky           # simulate randomly missing poll windows
        self.node_id: str | None = None
        self.client = httpx.Client(timeout=10.0)
        self._pending_results: list[dict] = []

    def register(self) -> None:
        resp = self.client.post(f"{self.base_url}/nodes/register", json={
            "tier": self.tier,
            "resources": {"cpu_cores": self.cpu, "ram_gb": self.ram,
                          "gpu_count": self.gpu, "gpu_vram_gb": self.gpu * 24.0},
            "region": self.region,
        })
        resp.raise_for_status()
        data = resp.json()
        self.node_id = data["node_id"]
        self.poll_interval = data.get("poll_interval_seconds", self.poll_interval)
        log.info("registered as node_id=%s (tier=%d, region=%s)", self.node_id, self.tier, self.region)

    def _execute(self, job: dict) -> dict:
        """Simulate running a job. Swap this for real container execution."""
        start = time.time()
        time.sleep(random.uniform(0.2, 0.8))  # pretend work
        success = random.random() > self.fail_rate
        latency_ms = (time.time() - start) * 1000
        return {
            "job_id": job["job_id"],
            "success": success,
            "latency_ms": latency_ms,
            "output": "ok" if success else None,
            "error": None if success else "simulated failure",
        }

    def poll_once(self) -> None:
        if self.flaky and random.random() < 0.15:
            log.info("simulating a missed poll window (flaky node)")
            return

        body = {
            "available_resources": {
                "cpu_cores": self.cpu, "ram_gb": self.ram,
                "gpu_count": self.gpu, "gpu_vram_gb": self.gpu * 24.0,
            },
            "completed_results": self._pending_results,
        }
        self._pending_results = []

        resp = self.client.post(f"{self.base_url}/nodes/{self.node_id}/poll", json=body)
        resp.raise_for_status()
        data = resp.json()

        assigned = data.get("assigned_job")
        if assigned:
            log.info("received job %s — executing", assigned["job_id"])
            result = self._execute(assigned)
            self._pending_results.append(result)
            log.info("job %s finished: success=%s latency=%.0fms",
                      result["job_id"], result["success"], result["latency_ms"])

    def run_forever(self) -> None:
        self.register()
        while True:
            try:
                self.poll_once()
            except httpx.HTTPError as e:
                log.warning("poll failed: %s", e)
            time.sleep(self.poll_interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="EdgeCompute Node Agent")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--tier", type=int, choices=[1, 2], default=2)
    ap.add_argument("--cpu", type=float, default=4.0)
    ap.add_argument("--ram", type=float, default=8.0)
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--region", default="nairobi-ke")
    ap.add_argument("--poll-interval", type=float, default=3.0)
    ap.add_argument("--fail-rate", type=float, default=0.0)
    ap.add_argument("--flaky", action="store_true", help="simulate a volunteer PC that sometimes misses polls")
    args = ap.parse_args()

    agent = NodeAgent(args.url, args.tier, args.cpu, args.ram, args.gpu,
                       args.region, args.poll_interval, args.fail_rate, args.flaky)
    agent.run_forever()


if __name__ == "__main__":
    main()
