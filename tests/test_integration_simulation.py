"""
Integration test: runs the FastAPI orchestrator in-process (a background
uvicorn thread on an ephemeral port) and drives a real NodeAgent + job
submission against it over HTTP — no manually started server, no external
services. This is what CI runs on every push.
"""
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pytest  # noqa: E402
import uvicorn  # noqa: E402

from agent.node_agent import NodeAgent  # noqa: E402
from orchestrator.main import app  # noqa: E402
from orchestrator.state import STORE  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def orchestrator_url():
    """Start orchestrator.main:app in a background thread on a free port."""
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            httpx.get(f"{base_url}/health", timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        pytest.fail("orchestrator did not become healthy in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5.0)

    # reset shared in-memory state between tests, since STORE is a module-level singleton
    STORE.nodes.clear()
    STORE.jobs.clear()
    STORE.queue.clear()


def test_health_endpoint_reports_zero_nodes_initially(orchestrator_url):
    resp = httpx.get(f"{orchestrator_url}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["active_nodes"] == 0


def test_submitted_job_reaches_completed_status_within_timeout(orchestrator_url):
    agent = NodeAgent(
        base_url=orchestrator_url, tier=2, cpu=4.0, ram=8.0, gpu=0,
        region="test-region", poll_interval=0.3, fail_rate=0.0, flaky=False,
    )
    agent.register()
    node_id = agent.node_id
    assert node_id is not None

    client = httpx.Client(timeout=10.0)
    submit = client.post(f"{orchestrator_url}/jobs", json={
        "payload": "integration-test-job",
        "requirements": {"cpu_cores": 1, "ram_gb": 1, "gpu_count": 0, "gpu_vram_gb": 0},
        "origin_lat": -1.28, "origin_lon": 36.82,
    })
    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    deadline = time.time() + 15.0
    status = None
    while time.time() < deadline:
        agent.poll_once()  # drive the pull-based loop explicitly, no real-time sleep needed
        job_resp = client.get(f"{orchestrator_url}/jobs/{job_id}")
        status = job_resp.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)

    assert status == "completed", f"job did not complete in time (last status: {status})"

    nodes_resp = client.get(f"{orchestrator_url}/nodes")
    node = next(n for n in nodes_resp.json() if n["node_id"] == node_id)
    assert node["credit_balance"] > 0, "serving node should have earned credits for the completed job"


def test_job_requiring_more_resources_than_any_node_has_stays_queued(orchestrator_url):
    agent = NodeAgent(
        base_url=orchestrator_url, tier=2, cpu=1.0, ram=1.0, gpu=0,
        region="test-region", poll_interval=0.3,
    )
    agent.register()

    client = httpx.Client(timeout=10.0)
    submit = client.post(f"{orchestrator_url}/jobs", json={
        "payload": "too-big-job",
        "requirements": {"cpu_cores": 64, "ram_gb": 256, "gpu_count": 8, "gpu_vram_gb": 320},
        "origin_lat": -1.28, "origin_lon": 36.82,
    })
    job_id = submit.json()["job_id"]

    agent.poll_once()
    job_resp = client.get(f"{orchestrator_url}/jobs/{job_id}")
    assert job_resp.json()["status"] == "queued"
