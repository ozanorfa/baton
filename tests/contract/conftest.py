from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixture_text():
    def load(provider: str, name: str) -> str:
        return (FIXTURES / provider / name).read_text(encoding="utf-8")

    return load
