import importlib

import pytest
from fastapi.testclient import TestClient

from aeris_server import app as app_module


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_off_on_vercel(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    assert TestClient(app_module.app).get(path).status_code == 200
    monkeypatch.setenv("VERCEL", "1")
    on_vercel = importlib.reload(app_module)
    try:
        assert TestClient(on_vercel.app).get(path).status_code == 404
    finally:
        monkeypatch.delenv("VERCEL")
        importlib.reload(app_module)
