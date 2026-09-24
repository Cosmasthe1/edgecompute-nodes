# EdgeCompute — Python Reference Implementation

Working, runnable implementation of the EdgeCompute orchestrator, node
agent, and simulator, matching the reconciled architecture (FastAPI
orchestrator, EWMA reliability scoring, pull-based/NAT-friendly polling,
credit-based incentive ledger).

This is the **Python-first** milestone: get the whole poll → assign →
execute → report → pay loop working end-to-end in one language before any
component gets ported to Go for performance.

## Layout

```
orchestrator/
  models.py       Pydantic models (Node, Job, poll/register/submit schemas)
  reliability.py  EWMA reliability scoring
  ledger.py       Credit payout calculation
  scheduler.py    Cost-function scheduling strategies (greedy, geographic,
                   power_aware, hybrid) + the convex utilization function
  state.py        In-memory store (swap point for Redis later)
  main.py         FastAPI app: /nodes/register, /nodes/{id}/poll, /jobs
agent/
  node_agent.py   Pull-based polling client (runs on volunteer PCs / XFRA nodes)
simulator/
  simulate.py     Spins up several simulated nodes + submits jobs, reports
                   JCT, success rate, and per-node credit earnings
```

## Running it

```bash
pip install -r requirements.txt

# terminal 1 — start the orchestrator
uvicorn orchestrator.main:app --reload --port 8000

# terminal 2 — run a real standalone agent (optional, for manual testing)
python agent/node_agent.py --url http://localhost:8000 --tier 2 --cpu 4 --ram 8

# terminal 2 (alternative) — run the full simulation instead
python simulator/simulate.py --url http://localhost:8000 --nodes 8 --jobs 20
```

Check `GET /health` or `GET /nodes` on the orchestrator at any time to see
live state.

## Testing

```bash
pip install -r requirements-dev.txt
ruff check .
pytest --cov=orchestrator --cov=agent --cov-report=term
```

41 tests, 88% line coverage on `orchestrator/` and `agent/`. This includes a
self-contained integration test (`tests/test_integration_simulation.py`)
that starts the FastAPI app in-process on an ephemeral port and drives a
real `NodeAgent` against it — no manually started server required, so it
runs the same way locally and in CI.

CI (`.github/workflows/ci.yml`) runs `ruff check` and the full test suite
with a coverage gate on every push, installing from `requirements.lock.txt`
for reproducible builds.

## What's implemented vs. deferred

| Piece | Status |
|---|---|
| FastAPI orchestrator, REST poll/register/submit | ✅ implemented |
| Pull-based polling (NAT-friendly) | ✅ implemented |
| EWMA reliability scoring | ✅ implemented (`reliability.py`) |
| Convex cost-function scheduler (greedy/geographic/power_aware/hybrid) | ✅ implemented (`scheduler.py`) |
| Credit-based incentive ledger | ✅ implemented (`ledger.py`) |
| Stale-node detection + missed-poll penalty + job requeue | ✅ implemented (`reap_stale_nodes`) |
| In-memory state | ✅ implemented — **swap point for Redis**, see `state.py` |
| Test suite (pytest, unit + in-process integration) | ✅ implemented — 41 tests, 88% coverage on `orchestrator/`+`agent/` |
| CI (lint + test on every push) | ✅ implemented (`.github/workflows/ci.yml`) |
| Pinned/reproducible dependencies | ✅ implemented (`requirements.lock.txt`, generated from a clean venv) |
| Real container execution (Docker) of job payloads | ⏳ stubbed — `NodeAgent._execute` currently simulates work with `sleep()`; swap for `docker run` |
| RL-based scheduling strategy | ⏳ not implemented — documented stretch goal in the proposal |
| Structured logging + Prometheus/Grafana metrics export | ⏳ not implemented — current logging is plain `logging.basicConfig`; `simulator/simulate.py` prints a text report instead |
| Dockerfile / devcontainer | ⏳ not implemented |
| Go rewrite of the hot path (poll endpoint / agent binary) | ⏳ next milestone, after load-testing this Python version to find the actual bottleneck |

## Design notes worth knowing when you extend this

- **`state.py` is the only place that touches shared dictionaries.** Every
  other module calls into `STORE`. This is deliberate: when you're ready to
  swap in Redis for the job queue, you only need to reimplement this one
  class's methods, not chase state access through the whole codebase.
- **The scheduler is a pure function of `(job, candidate_nodes)`.** It has
  no side effects and doesn't know about HTTP, which makes it trivial to
  unit test or drive directly from `simulator/simulate.py` without spinning
  up a server.
- **Reliability and credits update in the same code path** (`_handle_job_result`
  in `main.py`), since both are triggered by the same event — a job result
  arriving on a poll. Keeping them together avoids the two ever drifting
  out of sync.
- **`reap_stale_nodes()` is not wired to a scheduler yet** — call it from a
  background `asyncio` task, an APScheduler job, or a simple cron hitting a
  new `/admin/reap` endpoint. Left as a deliberate integration point rather
  than baked in, since how you want to trigger it may depend on your
  deployment (single process vs. multiple workers).

## Next steps toward the full project plan

1. Add Redis-backed `Store` implementation alongside the in-memory one.
2. Replace `NodeAgent._execute`'s simulated sleep with real Docker container
   execution of the job payload.
3. Load-test with `simulator/simulate.py` at higher `--nodes` / `--jobs`
   counts to find where the FastAPI orchestrator's poll-handling endpoint
   starts to strain — that's the empirical case for what to port to Go.
4. Wire Prometheus client metrics into `main.py` for the Phase 4 evaluation
   chapter (JCT, node utilization, energy per job, provider earnings).
