"""
Structured (JSON) logging for the orchestrator.

Plain-text logging.basicConfig output isn't machine-parseable, which
matters for a networked service someone might actually run — you can't
grep/aggregate/alert on free-text log lines in any serious operational
setup. This swaps in JSON-formatted records while keeping the exact same
log.info(...) / log.warning(...) call sites used throughout the codebase.
"""
from __future__ import annotations

import logging
import sys

from pythonjsonlogger import json as jsonlogger


def configure_json_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
