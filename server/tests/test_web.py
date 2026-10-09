import pytest
from fastapi.testclient import TestClient

from aeris_server.app import app
from aeris_server.auth import COOKIE_NAME

pytestmark = pytest.mark.usefixtures("api_tokens")


def _client(base_url: str = "https://aeris.example") -> TestClient:
    return TestClient(app, base_url=base_url, follow_redirects=False)


# Redirects to the login page.


def test_page_redirects_to_login() -> None:
    response = _client().get("/")
    assert (response.status_code, response.headers["location"]) == (303, "/login")


def test_htmx_request_redirects_to_login() -> None:
    response = _client().get("/", headers={"HX-Request": "true"})
    assert (response.status_code, response.headers["hx-redirect"]) == (200, "/login")


def test_invalid_cookie_redirects_to_login() -> None:
    client = TestClient(app, cookies={COOKIE_NAME: "wrong"}, follow_redirects=False)
    assert client.get("/").status_code == 303


# Login and logout.


def test_login_form() -> None:
    response = _client().get("/login")
    assert response.status_code == 200
    assert 'name="token"' in response.text


def test_login_invalid_token() -> None:
    response = _client().post("/login", data={"token": "wrong"})
    assert response.status_code == 401
    assert "Invalid token." in response.text
    assert "set-cookie" not in response.headers


def test_login(api_tokens: dict[str, str]) -> None:
    client = _client()
    response = client.post("/login", data={"token": f"  {api_tokens['ro']}  "})
    assert (response.status_code, response.headers["location"]) == (303, "/")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}={api_tokens['ro']};")
    for attribute in ["HttpOnly", "Max-Age=31536000", "Path=/", "SameSite=lax", "Secure"]:
        assert attribute in cookie
    # The client kept the cookie, so the home page now works.
    home = client.get("/")
    assert home.status_code == 200
    assert "Logged in as reader" in home.text


def test_login_on_localhost_is_not_secure(api_tokens: dict[str, str]) -> None:
    response = _client("http://localhost:8000").post("/login", data={"token": api_tokens["rw"]})
    assert response.status_code == 303
    assert "Secure" not in response.headers["set-cookie"]


def test_logout(api_tokens: dict[str, str]) -> None:
    client = _client()
    client.post("/login", data={"token": api_tokens["rw"]})
    response = client.post("/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/login")
    assert f'{COOKIE_NAME}="";' in response.headers["set-cookie"]
    assert client.get("/").status_code == 303
