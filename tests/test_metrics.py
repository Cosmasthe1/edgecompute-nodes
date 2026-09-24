"""Tests for Prometheus metrics endpoint exposed by the orchestrator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from orchestrator.main import app  # noqa: E402


def test_metrics_endpoint_returns_metrics():
    client = TestClient(app)

    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text

    # Ensure our metric names are present
    assert "edgecompute_jobs_submitted_total" in text
    assert "edgecompute_jobs_completed_total" in text
    assert "edgecompute_jobs_failed_total" in text
    assert "edgecompute_job_runtime_seconds" in text
