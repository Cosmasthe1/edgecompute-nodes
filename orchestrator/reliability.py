"""
EWMA-based reliability scoring.

Each node carries a single reliability_score in [0, 1]. Every time a node
finishes a job (success or failure) or misses a poll window (goes silent),
we fold a new observation into the score using an exponentially weighted
moving average so recent behavior dominates the signal without discarding
history entirely.

    score_new = alpha * observation + (1 - alpha) * score_old

A higher ALPHA makes the score react faster to recent events (good for
punishing a volunteer PC that just dropped off; also lets it recover
faster once it starts completing jobs again).
"""
from __future__ import annotations

ALPHA = 0.3          # smoothing factor: weight on the newest observation
TIMEOUT_PENALTY = 0.0  # observation value fed in when a node misses its poll window
MAX_LATENCY_MS_FOR_FULL_CREDIT = 2000.0  # jobs slower than this start losing credit


def _latency_observation(latency_ms: float) -> float:
    """Map job latency to an observation in [0, 1]. Fast job -> close to 1."""
    if latency_ms <= MAX_LATENCY_MS_FOR_FULL_CREDIT:
        return 1.0
    # decay smoothly past the threshold instead of a hard cliff
    return max(0.0, MAX_LATENCY_MS_FOR_FULL_CREDIT / latency_ms)


def update_on_job_result(current_score: float, success: bool, latency_ms: float) -> float:
    """Fold a completed (or failed) job into the node's reliability score."""
    if not success:
        observation = 0.0
    else:
        observation = _latency_observation(latency_ms)
    return ALPHA * observation + (1 - ALPHA) * current_score


def update_on_missed_poll(current_score: float) -> float:
    """Fold a missed poll window (node went quiet) into the score."""
    return ALPHA * TIMEOUT_PENALTY + (1 - ALPHA) * current_score
