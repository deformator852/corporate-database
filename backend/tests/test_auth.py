"""Sessions, sign-in throttling, revocation, WebSocket origin."""

from conftest import csrf, login, run


def test_login_and_me(client, make_user):
    _, email, password = make_user(["documents.list"])
    assert login(client, email, password).status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == email


def test_wrong_password_is_401_and_long_password_is_not_500(client, make_user):
    _, email, _ = make_user()
    assert login(client, email, "wrong-password").status_code == 401
    # bcrypt reads 72 bytes; 50 Cyrillic letters are 100 bytes.
    assert login(client, email, "п" * 50).status_code == 401


def test_login_throttled_after_five_failures(client, make_user):
    _, email, password = make_user()
    codes = [login(client, email, "wrong-password").status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    # Even the right password waits out the window.
    assert login(client, email, password).status_code == 429


def test_logout_revokes_access_token(client, make_user):
    _, email, password = make_user()
    login(client, email, password)
    token = client.cookies.get("my_token")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204
    client.cookies.set("my_token", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_refresh_token_is_single_use(client, make_user):
    _, email, password = make_user()
    login(client, email, password)
    old_refresh = client.cookies.get("my_refresh")
    headers = csrf(client, "csrf_refresh_token")
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 204
    client.cookies.set("my_refresh", old_refresh)
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 401


def test_password_change_signs_the_user_out(client, make_user):
    from fastapi.testclient import TestClient

    import main

    _, admin_email, admin_password = make_user(admin=True)
    user_id, email, password = make_user()
    with TestClient(main.app, base_url="https://testserver") as victim:
        login(victim, email, password)
        login(client, admin_email, admin_password)
        response = client.patch(
            f"/api/v1/users/{user_id}",
            headers=csrf(client),
            json={
                "first_name": "Test",
                "last_name": "User",
                "email": email,
                "role_keys": [],
                "password": "Changed-password-1",
            },
        )
        assert response.status_code == 200
        assert victim.get("/api/v1/auth/me").status_code == 401


def test_token_signed_with_another_key_is_401(client):
    import jwt

    forged = jwt.encode({"sub": "1", "type": "access", "exp": 9999999999}, "x" * 48, "HS256")
    client.cookies.set("my_token", forged)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_websocket_rejects_other_origins(client, make_user):
    _, email, password = make_user()
    login(client, email, password)
    token = client.cookies.get("my_token")

    def connect(origin: str) -> str:
        try:
            with client.websocket_connect(
                "/api/v1/notifications/ws",
                headers={"origin": origin, "cookie": f"my_token={token}"},
            ):
                return "open"
        except Exception as exc:  # noqa: BLE001
            return str(getattr(exc, "status_code", exc))

    assert connect("https://testserver") == "open"
    assert connect("https://evil.example") == "403"
    assert connect("https://testserver.evil.example") == "403"
