from fastapi.testclient import TestClient

from aeris_server.app import app

client = TestClient(app)


def test_static_file() -> None:
    response = client.get("/static/ping.txt")
    assert response.status_code == 200
    assert response.text == "pong\n"
