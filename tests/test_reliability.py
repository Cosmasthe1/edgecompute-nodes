"""
Tests for orchestrator.reliability: EWMA updates on job results and missed
poll windows.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from orchestrator.reliability import (  # noqa: E402
    ALPHA,
    update_on_job_result,
    update_on_missed_poll,
)


def test_successful_fast_job_increases_score_toward_one():
    score = 0.5
    new_score = update_on_job_result(score, success=True, latency_ms=100)
    assert new_score > score


def test_failed_job_decreases_score():
    score = 0.8
    new_score = update_on_job_result(score, success=False, latency_ms=100)
    assert new_score < score


def test_slow_success_helps_less_than_fast_success():
    score = 0.5
    fast = update_on_job_result(score, success=True, latency_ms=100)
    slow = update_on_job_result(score, success=True, latency_ms=20000)
    assert fast > slow


def test_missed_poll_decreases_score():
    score = 0.8
    new_score = update_on_missed_poll(score)
    assert new_score < score


def test_score_stays_in_zero_one_range_after_many_updates():
    score = 0.5
    for _ in range(200):
        score = update_on_job_result(score, success=True, latency_ms=50)
    assert 0.0 <= score <= 1.0

    score = 0.5
    for _ in range(200):
        score = update_on_job_result(score, success=False, latency_ms=50)
    assert 0.0 <= score <= 1.0


def test_repeated_failures_converge_toward_zero():
    score = 0.9
    for _ in range(50):
        score = update_on_job_result(score, success=False, latency_ms=100)
    assert score < 0.05


def test_repeated_fast_successes_converge_toward_one():
    score = 0.1
    for _ in range(50):
        score = update_on_job_result(score, success=True, latency_ms=100)
    assert score > 0.95


def test_recovery_after_failure_streak_with_subsequent_successes():
    score = 0.9
    for _ in range(10):
        score = update_on_job_result(score, success=False, latency_ms=100)
    low_point = score
    for _ in range(20):
        score = update_on_job_result(score, success=True, latency_ms=100)
    assert score > low_point


def test_alpha_is_a_valid_smoothing_factor():
    # sanity check on the module constant itself, since every test above
    # depends on it being in (0, 1]
    assert 0 < ALPHA <= 1
