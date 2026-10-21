from pathlib import Path

import pytest

FAKE_PROVIDER_DIR = Path(__file__).parent / "fake_provider"
FAKE_CLI = FAKE_PROVIDER_DIR / "fake_ai.py"


@pytest.fixture()
def fake_registry(monkeypatch):
    """The real registry with the fake provider discovered via the real
    entry-point mechanism (dist-info on sys.path) — validates T13 in every use."""
    monkeypatch.syspath_prepend(str(FAKE_PROVIDER_DIR))
    from ai_orchestrator.providers import load_all

    registry = load_all()
    assert "fake" in registry.names()
    return registry


@pytest.fixture()
def fake_project(tmp_path: Path, monkeypatch) -> Path:
    """A temp project whose pipeline runs planner → coder on the fake CLI."""
    project = tmp_path / "proj"
    (project / ".ai").mkdir(parents=True)
    (project / ".ai" / "config.yaml").write_text(
        "pipeline:\n"
        "  stages: [planner, coder]\n"
        "roles:\n"
        "  planner: {provider: fake}\n"
        "  coder: {provider: fake}\n"
        "providers:\n"
        f"  fake: {{command: {FAKE_CLI}, timeout_s: 30}}\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return project
