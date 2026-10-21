"""ADR-032: `batonai setup` — revise role→provider and provider→model later.

`apply_choices` is pure, so the merge semantics that matter (never clobber
unrelated config, clearing a pin, not inventing empty blocks) are tested
directly.
"""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app
from ai_orchestrator.cli.commands import setup as S
from ai_orchestrator.config.loader import load_config

runner = CliRunner()


def test_apply_sets_role_provider_and_model():
    doc = S.apply_choices({}, {"coder": "codex"}, {"codex": "o3"})
    assert doc["roles"]["coder"]["provider"] == "codex"
    assert doc["providers"]["codex"]["model"] == "o3"


def test_apply_preserves_unrelated_config():
    """A user's pipeline/timeouts must survive a model change untouched."""
    doc = {
        "pipeline": {"stages": ["planner", "coder"], "fix_loop": True},
        "roles": {"coder": {"provider": "claude", "enabled": True}},
        "providers": {"claude": {"timeout_s": 1200}},
    }
    out = S.apply_choices(doc, {}, {"claude": "haiku"})
    assert out["pipeline"] == {"stages": ["planner", "coder"], "fix_loop": True}
    assert out["roles"]["coder"]["enabled"] is True, "sibling keys are kept"
    assert out["providers"]["claude"] == {"timeout_s": 1200, "model": "haiku"}


def test_dash_clears_a_pin_back_to_the_cli_default():
    doc = {"providers": {"claude": {"model": "haiku", "timeout_s": 900}}}
    out = S.apply_choices(doc, {}, {"claude": "-"})
    assert "model" not in out["providers"]["claude"]
    assert out["providers"]["claude"]["timeout_s"] == 900


def test_clearing_the_only_key_removes_the_empty_block():
    """An empty `providers: {claude: {}}` is noise in a hand-read file."""
    out = S.apply_choices({"providers": {"claude": {"model": "haiku"}}}, {}, {"claude": "-"})
    assert "providers" not in out


def test_no_choices_is_a_no_op():
    doc = {"roles": {"coder": {"provider": "claude"}}}
    assert S.apply_choices(dict(doc), {}, {}) == doc


def test_written_config_is_valid_and_loadable(tmp_path: Path, monkeypatch):
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "config.yaml").write_text("roles:\n  coder: {provider: claude}\n",
        encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    doc = S.apply_choices(S._load_document(tmp_path), {"coder": "codex"}, {"codex": "o3"})
    S._write_document(tmp_path, doc)
    cfg = load_config(tmp_path, env={}).config
    assert cfg.roles["coder"].provider == "codex"
    assert cfg.providers["codex"].model == "o3"


def test_an_unknown_provider_is_refused_not_written(monkeypatch):
    """A typo'd provider would fail preflight later; catch it at the prompt."""
    monkeypatch.setattr(S.typer, "prompt", lambda *a, **k: "clode")  # typo
    chosen = S.choose_providers({"coder": "claude"}, ["claude", "codex"])
    assert chosen == {}, "unknown provider names are never written to config"


def test_model_answers_are_not_validated(monkeypatch):
    """Model ids change often; the CLI is the authority, not baton (ADR-031)."""
    monkeypatch.setattr(S.typer, "prompt", lambda *a, **k: "some-2029-model")
    result = S.choose_models({"claude": None}, ["claude"], {"claude": "claude"})
    assert result == {"claude": "some-2029-model"}


def test_setup_reports_when_nothing_changed(tmp_path, monkeypatch):
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "config.yaml").write_text("roles:\n  coder: {provider: claude}\n",
        encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(S.typer, "prompt", lambda *a, **k: "")  # Enter everywhere
    before = (tmp_path / ".ai" / "config.yaml").read_text(encoding="utf-8")
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 0 and "nothing changed" in result.output
    assert (tmp_path / ".ai" / "config.yaml").read_text(encoding="utf-8") == before, "file untouched"


def test_setup_shows_the_current_assignment_first(tmp_path, monkeypatch):
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "config.yaml").write_text("roles:\n  coder: {provider: claude}\n",
        encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(S.typer, "prompt", lambda *a, **k: "")
    out = runner.invoke(app, ["setup"]).output
    assert "current setup" in out and "coder" in out and "claude" in out


def test_setup_writes_loadable_yaml_end_to_end(tmp_path, monkeypatch):
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "config.yaml").write_text("roles:\n  coder: {provider: claude}\n",
        encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    answers = iter(["", "", "codex", "", "", "haiku", ""] * 3)
    monkeypatch.setattr(S.typer, "prompt", lambda *a, **k: next(answers, ""))
    assert runner.invoke(app, ["setup"]).exit_code == 0
    assert yaml.safe_load((tmp_path / ".ai" / "config.yaml").read_text(encoding="utf-8")) is not None


def test_each_provider_is_asked_about_once(tmp_path, monkeypatch):
    """planner and reviewer share codex by default; asking 3x exhausts input."""
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "config.yaml").write_text(
        "roles:\n  planner: {provider: codex}\n  coder: {provider: codex}\n"
        "  reviewer: {provider: codex}\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    asked: list[str] = []
    monkeypatch.setattr(S.typer, "prompt", lambda label, **k: asked.append(label) or "")
    runner.invoke(app, ["setup"])
    model_prompts = [a for a in asked if "CLI default" in a]
    assert len(model_prompts) == len(set(model_prompts)), model_prompts
