"""Structured JSONL event log, one file per run (ARCHITECTURE.md §6).

Machine-readable stream for tooling; human-facing output lives in
cli/render.py — one event source, two renderings.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG_FILENAME = "orchestrator.jsonl"

# Canonical event names (free-form extras allowed, these are the core protocol).
RUN_STARTED = "run_started"
RUN_RESUMED = "run_resumed"
RUN_REVISED = "run_revised"
STAGE_STARTED = "stage_started"
PROVIDER_INVOKED = "provider_invoked"
STAGE_SUCCEEDED = "stage_succeeded"
STAGE_FAILED = "stage_failed"
STAGE_SKIPPED = "stage_skipped"
RUN_FINISHED = "run_finished"


class EventLog:
    def __init__(self, logs_dir: Path, sink: Callable[[dict[str, Any]], None] | None = None):
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / LOG_FILENAME
        self.sink = sink  # optional live listener (e.g. CLI progress rendering)

    def emit(self, event: str, **fields: Any) -> None:
        record = {"ts": datetime.now(UTC).isoformat(), "event": event, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        if self.sink is not None:
            self.sink(record)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]
