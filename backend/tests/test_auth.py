"""Sessions, sign-in throttling, revocation, WebSocket origin."""

import time

from conftest import csrf, login


def test_login_and_me(client, make_user):
    _, email, password = make_user(["documents.list"])
    assert login(client, email, password).status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == email


def test_wrong_password_is_401_and_long_password_is_not_500(client, make_user):
    _, email, _ = make_user()
    assert login(client, email, "wrong-password").status_code == 401
    # bcrypt reads 72 bytes; 50 Cyrillic letters are 100 bytes.
    assert login(client, email, "п" * 50).status_code == 401


def test_an_unknown_email_costs_a_password_check_too(client, monkeypatch):
    import services.auth

    checked: list[str] = []
    real = services.auth.verify_password

    def spy(plain: str, hashed: str) -> bool:
        checked.append(plain)
        return real(plain, hashed)

    monkeypatch.setattr(services.auth, "verify_password", spy)

    response = login(client, "nobody-here@corpus.test", "some-password")

    # Answering without the (slow) check would tell which emails have accounts.
    assert response.status_code == 401 and checked == ["some-password"]


def test_users_change_their_own_password_and_sign_in_again(client, make_user):
    _, email, password = make_user()
    login(client, email, password)

    def change(current: str, new: str):
        return client.post(
            "/api/v1/auth/password", headers=csrf(client), json={"current_password": current, "new_password": new}
        )

    wrong = change("wrong-password", "New-password-1")
    assert (wrong.status_code, wrong.json()["message"]) == (400, "The current password is wrong.")
    assert change(password, password).status_code == 400
    assert change(password, "short").status_code == 400

    assert change(password, "New-password-1").status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401  # this session ended too
    assert login(client, email, password).status_code == 401
    # Sessions issued in the second of the change end too (1 s token precision).
    time.sleep(1.1)
    assert login(client, email, "New-password-1").status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == email


def test_wrong_current_passwords_are_throttled_like_sign_ins(client, make_user):
    _, email, password = make_user()
    login(client, email, password)
    body = {"current_password": "wrong-password", "new_password": "New-password-1"}
    codes = [client.post("/api/v1/auth/password", headers=csrf(client), json=body).status_code for _ in range(6)]
    assert codes == [400] * 5 + [429]


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


def test_disabled_user_is_signed_out_and_cannot_sign_in(client, make_user):
    from fastapi.testclient import TestClient

    import main

    _, admin_email, admin_password = make_user(admin=True)
    user_id, email, password = make_user(["documents.list"])
    with TestClient(main.app, base_url="https://testserver") as employee:
        login(employee, email, password)
        login(client, admin_email, admin_password)
        response = client.post(f"/api/v1/users/{user_id}/disable", headers=csrf(client))
        assert response.status_code == 200 and response.json()["disabled"] is True
        assert employee.get("/api/v1/auth/me").status_code == 401
        refresh = employee.post("/api/v1/auth/refresh", headers=csrf(employee, "csrf_refresh_token"))
        assert refresh.status_code == 401
        # Wrong password: the same answer as for anyone else.
        assert login(employee, email, "wrong-password").status_code == 401
        assert login(employee, email, password).status_code == 403
        # The account and its history stay; enabling restores sign-in.
        assert client.get(f"/api/v1/users/{user_id}").json()["disabled"] is True
        assert client.post(f"/api/v1/users/{user_id}/enable", headers=csrf(client)).status_code == 200
        assert login(employee, email, password).status_code == 200


def test_cannot_disable_self_or_a_stronger_account(client, make_user):
    admin_id, _, _ = make_user(admin=True)
    user_id, email, password = make_user(["users.list", "users.disable"])
    login(client, email, password)
    assert client.post(f"/api/v1/users/{user_id}/disable", headers=csrf(client)).status_code == 409
    assert client.post(f"/api/v1/users/{admin_id}/disable", headers=csrf(client)).status_code == 403


def test_a_disabled_account_rejects_even_a_freshly_issued_token(client, make_user):
    # Defense in depth: disabling also ends old sessions by time, but a token
    # minted afterwards (clock skew, a bug) must still not work.
    import time

    from security import security

    _, admin_email, admin_password = make_user(admin=True)
    user_id, _, _ = make_user()
    login(client, admin_email, admin_password)
    client.post(f"/api/v1/users/{user_id}/disable", headers=csrf(client))
    time.sleep(1.1)  # past the sessions cutoff second
    token = security.create_access_token(uid=str(user_id))
    client.cookies.set("my_token", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_auth_errors_use_the_common_shape(client, make_user):
    user_id, email, password = make_user(["users.disable"])
    login(client, email, password)
    # A change without the CSRF header: refused, but the session stays valid.
    missing_csrf = client.post(f"/api/v1/users/{user_id}/disable")
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "forbidden"
    assert client.get("/api/v1/auth/me").status_code == 200
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").json() == {"code": "unauthorized", "message": "Not authenticated"}
