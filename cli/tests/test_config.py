from pathlib import Path

import pytest

from aeris_cli.config import ConfigError, load_config


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aeris.yaml"
    monkeypatch.setenv("AERIS_CONFIG_PATH", str(path))
    monkeypatch.delenv("AERIS_URL", raising=False)
    monkeypatch.delenv("AERIS_TOKEN", raising=False)
    return path


def test_from_file(config_file: Path) -> None:
    config_file.write_text("url: https://aeris.example/\ntoken: secret\n")
    config = load_config()
    assert (config.url, config.token) == ("https://aeris.example", "secret")


def test_env_wins_key_by_key(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file.write_text("url: https://file.example\ntoken: file-secret\n")
    monkeypatch.setenv("AERIS_URL", "https://env.example")
    config = load_config()
    assert (config.url, config.token) == ("https://env.example", "file-secret")


def test_env_only(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AERIS_URL", "https://env.example")
    monkeypatch.setenv("AERIS_TOKEN", "env-secret")
    assert load_config().token == "env-secret"


@pytest.mark.parametrize(
    "content", [None, "", "database_url: postgresql://old\n", "url: https://x\n"]
)
def test_missing(config_file: Path, content: str | None) -> None:
    if content is not None:
        config_file.write_text(content)
    with pytest.raises(ConfigError, match="Set AERIS_URL and AERIS_TOKEN"):
        load_config()


def test_not_a_mapping(config_file: Path) -> None:
    config_file.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError, match="key: value"):
        load_config()


def test_token_not_in_repr(config_file: Path) -> None:
    config_file.write_text("url: https://x\ntoken: hush\n")
    assert "hush" not in repr(load_config())
