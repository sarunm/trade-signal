from pathlib import Path

from config import Settings


def test_api_uses_pydantic_v2_config_style():
    api_dir = Path(__file__).resolve().parents[1] / "api"

    offenders = [
        path.relative_to(api_dir.parent).as_posix()
        for path in api_dir.rglob("*.py")
        if "class Config:" in path.read_text()
    ]

    assert offenders == []


def test_settings_loads_database_url_from_env(monkeypatch):
    database_url = "postgresql+asyncpg://env-user:env-pass@env-db:5432/env-name"

    monkeypatch.setenv("DATABASE_URL", database_url)

    assert Settings().database_url == database_url
