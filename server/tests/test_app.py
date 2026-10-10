import pytest
from fastapi.testclient import TestClient

from aeris_server.app import app

pytestmark = pytest.mark.usefixtures("api_tokens")


@pytest.mark.parametrize(
    ("path", "login"),
    [("/docs", "/login?next=%2Fdocs"), ("/openapi.json", "/login?next=%2Fopenapi.json")],
)
def test_api_docs_require_login(path: str, login: str) -> None:
    response = TestClient(app, follow_redirects=False).get(path)
    assert (response.status_code, response.headers["location"]) == (303, login)


def test_api_docs_with_login(api_tokens: dict[str, str]) -> None:
    client = TestClient(app, headers={"Authorization": f"Bearer {api_tokens['ro']}"})
    docs = client.get("/docs")
    assert docs.status_code == 200 and "swagger-ui" in docs.text
    assert "/openapi.json" in docs.text


def test_redoc_is_off(api_tokens: dict[str, str]) -> None:
    client = TestClient(app, headers={"Authorization": f"Bearer {api_tokens['ro']}"})
    assert client.get("/redoc").status_code == 404


def test_schema_lists_the_api_with_bearer_auth(api_tokens: dict[str, str]) -> None:
    client = TestClient(app, cookies={"aeris_token": api_tokens["ro"]})
    schema = client.get("/openapi.json").json()
    assert all(path.startswith("/api/") or path == "/healthz" for path in schema["paths"])
    assert "/api/notes/{note_id}" in schema["paths"]
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/api/tags"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in schema["paths"]["/healthz"]["get"]
