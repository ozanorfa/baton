from pathlib import Path

from ai_orchestrator.observability import events
from ai_orchestrator.observability.events import EventLog


def test_fake_run_replay_is_parseable_and_ordered(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "logs")

    log.emit(events.RUN_STARTED, run_id="r1", request="add X")
    log.emit(events.STAGE_STARTED, stage="planner", provider="codex")
    log.emit(events.PROVIDER_INVOKED, stage="planner", provider="codex", timeout_s=600)
    log.emit(events.STAGE_SUCCEEDED, stage="planner", duration_s=1.5)
    log.emit(events.STAGE_SKIPPED, stage="designer", reason="disabled")
    log.emit(events.STAGE_FAILED, stage="coder", error="exit 1")
    log.emit(events.RUN_FINISHED, run_id="r1", status="failed")

    records = log.read()
    assert [r["event"] for r in records] == [
        events.RUN_STARTED,
        events.STAGE_STARTED,
        events.PROVIDER_INVOKED,
        events.STAGE_SUCCEEDED,
        events.STAGE_SKIPPED,
        events.STAGE_FAILED,
        events.RUN_FINISHED,
    ]
    timestamps = [r["ts"] for r in records]
    assert timestamps == sorted(timestamps)  # ISO-8601 sorts chronologically
    assert all("ts" in r and "event" in r for r in records)
    assert records[2]["timeout_s"] == 600


def test_read_missing_file_is_empty(tmp_path: Path) -> None:
    assert EventLog(tmp_path / "logs").read() == []


def test_non_serializable_fields_are_stringified(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "logs")
    log.emit(events.RUN_STARTED, path=Path("/tmp/x"))
    assert log.read()[0]["path"] == str(Path("/tmp/x"))  # OS-native spelling
