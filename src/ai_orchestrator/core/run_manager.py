"""Run directory ownership and the run state machine (ARCHITECTURE.md §2.4).

All state lives on disk; run.json is rewritten atomically (temp file + rename)
on every transition so a crash at any point leaves the previous consistent
state intact. This is what makes `ai resume` possible (ADR-005).
"""

import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from ai_orchestrator.core.models import RunState, StageResult, StageSpec

RUNS_SUBDIR = Path(".ai") / "runs"
RUN_FILE = "run.json"
_SUBDIRS = ("artifacts", "prompts", "logs")


class RunManager:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.runs_dir = project_dir / RUNS_SUBDIR

    # -- creation & loading ------------------------------------------------

    def new_run_id(self) -> str:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M")
        return f"{stamp}_{secrets.token_hex(2)}"

    def create_run(self, request: str, stages: list[StageSpec]) -> RunState:
        # ids have minute granularity + 2 random bytes; retry on the rare
        # collision (e.g. concurrent runs in one project) instead of crashing
        for attempt in range(5):
            run_id = self.new_run_id()
            run_dir = self.runs_dir / run_id
            try:
                (run_dir / _SUBDIRS[0]).mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                if attempt == 4:
                    raise
        for sub in _SUBDIRS[1:]:
            (run_dir / sub).mkdir(parents=True, exist_ok=False)
        state = RunState(
            run_id=run_id,
            request=request,
            project_dir=self.project_dir,
            stages=[StageResult(name=s.name, role=s.role) for s in stages],
        )
        self.save(state)
        return state

    def load_run(self, run_id: str) -> RunState:
        path = self.run_dir(run_id) / RUN_FILE
        if not path.is_file():
            raise FileNotFoundError(f"no run {run_id!r} under {self.runs_dir}")
        return RunState.model_validate_json(path.read_text())

    def list_run_ids(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(p.name for p in self.runs_dir.iterdir() if (p / RUN_FILE).is_file())

    def latest_run_id(self) -> str | None:
        """The most recent run id (ids sort ascending by timestamp), or None."""
        ids = self.list_run_ids()
        return ids[-1] if ids else None

    # -- persistence -------------------------------------------------------

    def save(self, state: RunState) -> None:
        """Atomic write: crash between write and rename leaves the old file intact."""
        path = self.run_dir(state.run_id) / RUN_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(state.model_dump_json(indent=2))
        os.replace(tmp, path)

    def save_artifact(self, state: RunState, name: str, content: str) -> Path:
        path = self.artifacts_dir(state.run_id) / name
        path.write_text(content)
        return path

    def load_artifact(self, state: RunState, name: str) -> str:
        return (self.artifacts_dir(state.run_id) / name).read_text()

    def save_prompt(self, state: RunState, position: int, stage_name: str, prompt: str) -> Path:
        path = self.run_dir(state.run_id) / "prompts" / f"{position:02d}-{stage_name}.md"
        path.write_text(prompt)
        return path

    # -- paths ---------------------------------------------------------------

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def artifacts_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "artifacts"

    def logs_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "logs"
