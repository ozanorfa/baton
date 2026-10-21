"""0.1.0 rename: the user config lives under ~/.config/batonai/, and a file left
under the pre-release name (~/.config/ai-orchestrator/) is still honoured."""

from pathlib import Path

from ai_orchestrator.config.loader import user_config_path


def test_new_path_is_the_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert user_config_path() == tmp_path / "batonai" / "config.yaml"


def test_legacy_file_is_used_when_no_new_one_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    legacy = tmp_path / "ai-orchestrator" / "config.yaml"
    legacy.parent.mkdir()
    legacy.write_text("providers: {claude: {model: haiku}}\n", encoding="utf-8")
    assert user_config_path() == legacy


def test_new_file_wins_over_legacy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for name in ("ai-orchestrator", "batonai"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "config.yaml").write_text("{}\n", encoding="utf-8")
    assert user_config_path() == tmp_path / "batonai" / "config.yaml"
