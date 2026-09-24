"""
Tests for orchestrator.logging_config: verifies log records are emitted as
valid, parseable JSON carrying the job_id/node_id context fields the
orchestrator attaches via `extra=`.
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.logging_config import configure_json_logging, get_logger  # noqa: E402


def test_log_record_is_valid_json_with_job_id_field(capsys):
    configure_json_logging()
    log = get_logger("edgecompute.test")

    log.info("job queued", extra={"job_id": "abc123", "cpu_cores": 2})

    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    record = json.loads(line)  # raises if not valid JSON

    assert record["job_id"] == "abc123"
    assert record["cpu_cores"] == 2
    assert record["message"] == "job queued"
    assert record["level"] == "INFO"


def test_log_record_carries_node_id_field(capsys):
    configure_json_logging()
    log = get_logger("edgecompute.test")

    log.info("job assigned", extra={"job_id": "j1", "node_id": "n1"})

    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    record = json.loads(line)

    assert record["node_id"] == "n1"
    assert record["job_id"] == "j1"


def test_warning_level_is_preserved_in_json_output(capsys):
    configure_json_logging()
    log = get_logger("edgecompute.test")

    log.warning("result for unknown job", extra={"job_id": "ghost-job"})

    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    record = json.loads(line)

    assert record["level"] == "WARNING"
    assert record["job_id"] == "ghost-job"


def test_configure_json_logging_sets_requested_level():
    configure_json_logging(level=logging.WARNING)
    assert logging.getLogger().level == logging.WARNING
    configure_json_logging(level=logging.INFO)  # restore default for other tests
