from pathlib import Path

import yaml
from typer.testing import CliRunner

from ai_orchestrator.cli.app import app
from ai_orchestrator.config.loader import load_config
from ai_orchestrator.config.schema import AppConfig

runner = CliRunner()


def test_init_creates_documented_footprint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    assert (tmp_path / ".ai" / "config.yaml").is_file()
    assert (tmp_path / ".ai" / "project.md").is_file()
    assert (tmp_path / ".ai" / "prompts").is_dir()
    # ADR-027: the ignore rule lives inside the directory baton owns, and the
    # project's root .gitignore is never touched.
    assert "runs/" in (tmp_path / ".ai" / ".gitignore").read_text(encoding="utf-8")
    assert not (tmp_path / ".gitignore").exists()

    # the starter config must be loadable and valid against the schema
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    loaded = load_config(tmp_path, env={})
    assert isinstance(loaded.config, AppConfig)
    assert loaded.config.roles["coder"].provider == "claude"


def test_init_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    (tmp_path / ".ai" / "project.md").write_text("MY CUSTOM PROFILE", encoding="utf-8")

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "nothing to do" in result.output
    assert (tmp_path / ".ai" / "project.md").read_text(encoding="utf-8") == "MY CUSTOM PROFILE"  # never clobbered
    assert (tmp_path / ".ai" / ".gitignore").read_text(encoding="utf-8").count("runs/") == 1  # no duplicate entry


def test_init_leaves_the_users_root_gitignore_untouched(tmp_path: Path, monkeypatch) -> None:
    """ADR-027: baton edits only files it owns."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    runner.invoke(app, ["init"])
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n", "unmodified, byte for byte"
    assert "runs/" in (tmp_path / ".ai" / ".gitignore").read_text(encoding="utf-8")


def test_init_respects_a_legacy_root_gitignore_entry(tmp_path: Path, monkeypatch) -> None:
    """A project set up by an older baton keeps working — no duplicate rule."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("# AI orchestrator run history (local)\n.ai/runs/\n",
        encoding="utf-8")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert not (tmp_path / ".ai" / ".gitignore").exists(), "the existing rule already covers it"
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").count(".ai/runs/") == 1


def test_starter_config_yaml_is_valid_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    data = yaml.safe_load((tmp_path / ".ai" / "config.yaml").read_text(encoding="utf-8"))
    assert data["roles"]["designer"]["enabled"] is False


def test_init_detects_stack_from_marker_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "pubspec.yaml").write_text("name: app\n", encoding="utf-8")
    runner.invoke(app, ["init"])
    profile = (tmp_path / ".ai" / "project.md").read_text(encoding="utf-8")
    assert "Detected: Flutter/Dart (pubspec.yaml); Python (pyproject.toml)" in profile
    assert "e.g.:" not in profile.split("## Structure")[0]  # no framework name-dropping


def test_init_without_markers_stays_neutral(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    profile = (tmp_path / ".ai" / "project.md").read_text(encoding="utf-8")
    assert "Nothing was auto-detected" in profile
    assert "Flutter" not in profile  # no misleading framework examples anywhere
    assert "Riverpod" not in profile


# ── ADR-031: model choice offered at setup ──────────────────────────────────

from ai_orchestrator.cli.commands import init as I  # noqa: E402


def test_render_model_block_is_empty_when_nothing_chosen() -> None:
    """Pressing Enter everywhere must leave the config byte-identical."""
    assert I.render_model_block({}) == ""


def test_render_model_block_is_valid_loadable_yaml(tmp_path: Path, monkeypatch) -> None:
    block = I.render_model_block({"claude": "haiku", "codex": "o3"})
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "config.yaml").write_text(I.STARTER_CONFIG + block, encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    loaded = load_config(tmp_path, env={})
    assert loaded.config.providers["claude"].model == "haiku"
    assert loaded.config.providers["codex"].model == "o3"
    assert loaded.config.roles["coder"].provider == "claude", "roles still intact"


def test_init_without_a_terminal_never_prompts(tmp_path: Path, monkeypatch) -> None:
    """`batonai init` in a script must not block on input."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(I, "_interactive", lambda: False)
    monkeypatch.setattr(
        I, "prompt_models", lambda p: (_ for _ in ()).throw(AssertionError("prompted"))
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "providers:" not in (tmp_path / ".ai" / "config.yaml").read_text(encoding="utf-8").replace(
        "#   claude", ""
    ).replace("# providers:", "")


def test_init_writes_the_chosen_models(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(I, "_interactive", lambda: True)
    monkeypatch.setattr(I, "prompt_models", lambda providers: {"claude": "haiku"})
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert load_config(tmp_path, env={}).config.providers["claude"].model == "haiku"


def test_no_models_flag_skips_the_question(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(I, "_interactive", lambda: True)
    monkeypatch.setattr(
        I, "prompt_models", lambda p: (_ for _ in ()).throw(AssertionError("prompted"))
    )
    assert runner.invoke(app, ["init", "--no-models"]).exit_code == 0


def test_rerunning_init_does_not_re_ask(tmp_path: Path, monkeypatch) -> None:
    """Existing files are kept, so a second question would imply an edit that
    never happens — the answer would be silently discarded."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(I, "_interactive", lambda: True)
    monkeypatch.setattr(I, "prompt_models", lambda providers: {"claude": "haiku"})
    runner.invoke(app, ["init"])
    monkeypatch.setattr(
        I, "prompt_models", lambda p: (_ for _ in ()).throw(AssertionError("re-asked"))
    )
    assert runner.invoke(app, ["init"]).exit_code == 0


def test_an_unknown_model_string_is_passed_through_unvalidated(tmp_path: Path) -> None:
    """Model ids are vendor-specific and change often; the CLI is the authority."""
    block = I.render_model_block({"claude": "some-future-model-2029"})
    assert "some-future-model-2029" in block


def test_prompt_label_carries_no_rich_markup(monkeypatch) -> None:
    """typer.prompt writes to the stream raw — markup would print literally."""
    seen: list[str] = []
    monkeypatch.setattr(I.typer, "prompt", lambda label, **kw: seen.append(label) or "")
    I.prompt_models(["claude", "codex"])
    assert seen and not any("[dim]" in s or "[/" in s for s in seen), seen
