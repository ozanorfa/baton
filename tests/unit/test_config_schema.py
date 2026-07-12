from importlib.resources import files

import pytest
import yaml
from pydantic import ValidationError

from ai_orchestrator.config.schema import AppConfig, warn_unknown_keys


def load_defaults() -> dict:
    text = (files("ai_orchestrator.config") / "defaults.yaml").read_text()
    return yaml.safe_load(text)


def test_defaults_yaml_is_valid() -> None:
    config = AppConfig.model_validate(load_defaults())
    assert config.pipeline.stages == ["planner", "designer", "coder", "reviewer", "publisher"]
    assert config.roles["coder"].provider == "claude"
    assert config.roles["designer"].enabled is False
    assert config.roles["publisher"].enabled is False  # opt-in (ADR-014)
    assert config.providers["claude"].timeout_s == 900
    assert warn_unknown_keys(config, "defaults.yaml") == []


def test_bad_value_fails_with_key_in_message() -> None:
    data = load_defaults()
    data["providers"]["claude"]["timeout_s"] = -5
    with pytest.raises(ValidationError, match="timeout_s"):
        AppConfig.model_validate(data)


def test_stage_without_role_fails() -> None:
    data = load_defaults()
    data["pipeline"]["stages"].append("tester")
    with pytest.raises(ValidationError, match="'tester' has no entry under 'roles'"):
        AppConfig.model_validate(data)


def test_role_with_unknown_provider_fails() -> None:
    data = load_defaults()
    data["roles"]["coder"]["provider"] = "mystery"
    with pytest.raises(ValidationError, match="unknown provider 'mystery'"):
        AppConfig.model_validate(data)


def test_unknown_keys_warn() -> None:
    data = load_defaults()
    data["pipeline"]["paralellism"] = 4  # typo'd key at a nested level
    data["telemetry"] = True  # unknown top-level key
    config = AppConfig.model_validate(data)
    with pytest.warns(UserWarning, match="unknown config keys in test.yaml") as record:
        found = warn_unknown_keys(config, "test.yaml")
    assert sorted(found) == ["pipeline.paralellism", "telemetry"]
    assert len(record) == 1
