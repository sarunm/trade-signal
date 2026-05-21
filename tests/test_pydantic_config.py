from pathlib import Path


def test_api_uses_pydantic_v2_config_style():
    api_dir = Path(__file__).resolve().parents[1] / "api"

    offenders = [
        path.relative_to(api_dir.parent).as_posix()
        for path in api_dir.rglob("*.py")
        if "class Config:" in path.read_text()
    ]

    assert offenders == []
