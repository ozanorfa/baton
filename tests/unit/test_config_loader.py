from pathlib import Path

import pytest

from ai_orchestrator.config.loader import ConfigError, load_config


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


@pytest.fixture()
def user_cfg(tmp_path: Path) -> Path:
    return tmp_path / "userhome" / "config.yaml"


def load(project: Path, user_cfg: Path, **kw):
    kw.setdefault("env", {})
    return load_config(project, user_path=user_cfg, **kw)


def test_defaults_only(project: Path, user_cfg: Path) -> None:
    loaded = load(project, user_cfg)
    assert loaded.config.roles["coder"].provider == "claude"
    assert loaded.source_of("roles.coder.provider") == "defaults"
    assert loaded.files_read == []


def test_user_overrides_defaults(project: Path, user_cfg: Path) -> None:
    write(user_cfg, "providers:\n  claude:\n    timeout_s: 1200\n")
    loaded = load(project, user_cfg)
    assert loaded.config.providers["claude"].timeout_s == 1200
    # deep merge: sibling keys from defaults survive
    assert loaded.config.providers["claude"].command == "claude"
    assert loaded.source_of("providers.claude.timeout_s").startswith("user (")
    assert loaded.source_of("providers.claude.command") == "defaults"


def test_project_overrides_user(project: Path, user_cfg: Path) -> None:
    write(user_cfg, "roles:\n  planner:\n    provider: claude\n")
    write(project / ".ai" / "config.yaml", "roles:\n  planner:\n    provider: gemini\n")
    loaded = load(project, user_cfg)
    assert loaded.config.roles["planner"].provider == "gemini"
    assert loaded.source_of("roles.planner.provider").startswith("project (")
    assert loaded.files_read == [user_cfg, project / ".ai" / "config.yaml"]


def test_env_overrides_project(project: Path, user_cfg: Path) -> None:
    write(project / ".ai" / "config.yaml", "providers:\n  codex:\n    timeout_s: 100\n")
    env = {"AI_ORCH_PROVIDERS__CODEX__TIMEOUT_S": "200"}
    loaded = load(project, user_cfg, env=env)
    assert loaded.config.providers["codex"].timeout_s == 200
    assert loaded.source_of("providers.codex.timeout_s") == "env (AI_ORCH_*)"


def test_cli_overrides_env(project: Path, user_cfg: Path) -> None:
    env = {"AI_ORCH_ROLES__REVIEWER__PROVIDER": "gemini"}
    loaded = load(project, user_cfg, env=env, overrides={"roles.reviewer.provider": "claude"})
    assert loaded.config.roles["reviewer"].provider == "claude"
    assert loaded.source_of("roles.reviewer.provider") == "cli"


def test_invalid_value_names_the_source_file(project: Path, user_cfg: Path) -> None:
    write(project / ".ai" / "config.yaml", "providers:\n  claude:\n    timeout_s: -1\n")
    with pytest.raises(ConfigError) as excinfo:
        load(project, user_cfg)
    message = str(excinfo.value)
    assert "providers.claude.timeout_s" in message
    assert str(project / ".ai" / "config.yaml") in message


def test_non_mapping_file_rejected(project: Path, user_cfg: Path) -> None:
    write(project / ".ai" / "config.yaml", "- just\n- a list\n")
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        load(project, user_cfg)


def test_missing_files_tolerated(project: Path, user_cfg: Path) -> None:
    loaded = load(project, user_cfg)  # neither user nor project file exists
    assert loaded.config.pipeline.stages[0] == "planner"
