from fastapi.testclient import TestClient

from aeris_server.app import app

client = TestClient(app)


def test_static_file() -> None:
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
