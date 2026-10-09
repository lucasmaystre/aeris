"""Where the server is and how to authenticate: `AERIS_URL` and `AERIS_TOKEN`, else `url` and
`token` in `~/.aeris.yaml` (or the file named by `AERIS_CONFIG_PATH`)."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    url: str
    token: str = field(repr=False)


def config_path() -> Path:
    return Path(os.environ.get("AERIS_CONFIG_PATH", Path.home() / ".aeris.yaml"))


def load_config() -> Config:
    """Environment variables win over the config file, key by key."""
    path = config_path()
    stored = _read(path)
    url = os.environ.get("AERIS_URL") or stored.get("url")
    token = os.environ.get("AERIS_TOKEN") or stored.get("token")
    if not url or not token:
        raise ConfigError(f"Set AERIS_URL and AERIS_TOKEN, or `url` and `token` in {path}.")
    return Config(url=str(url).rstrip("/"), token=str(token))


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain `key: value` lines.")
    return data
