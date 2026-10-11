"""Single sign-on (OpenID Connect) against a stand-in identity provider that
signs ID tokens with its own key and checks PKCE and the client secret."""

import base64
import hashlib
import json
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import csrf, login
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

ISSUER = "https://idp.acme.test/realms/acme"
CLIENT_ID = "corpus"
SECRET = "client-secret-" + "s" * 20


class FakeProvider:
    """Answers discovery, keys and token requests like a real provider."""

    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
        self.codes: dict[str, dict] = {}
        # What the next sign-in returns; tests change it.
        self.claims: dict = {}
        self.dialed: list[tuple[str, str, object]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        # The address it was sent to, the host it speaks to and the TLS name.
        sni = request.extensions.get("sni_hostname")
        self.dialed.append((request.url.netloc.decode(), request.headers["host"], sni))
        url = f"https://{request.headers['host']}{request.url.raw_path.decode().split('?')[0]}"
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/certs",
                },
            )
        if url == f"{ISSUER}/certs":
            return httpx.Response(200, json=KeySet([self.key]).as_dict(private=False))
        if url == f"{ISSUER}/token":
            form = parse_qs(request.content.decode())
            grant = self.codes.pop(form["code"][0], None)
            verifier = form["code_verifier"][0].encode()
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=").decode()
            if grant is None or form["client_secret"][0] != SECRET or challenge != grant["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": grant["id_token"]})
        return httpx.Response(404)

    def approve(self, authorize_url: str, *, key: RSAKey | None = None, **overrides) -> str:
        """The user signed in at the provider: a code for the callback."""
        query = parse_qs(urlsplit(authorize_url).query)
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": query["nonce"][0],
            **self.claims,
            **overrides,
        }
        token = jwt.encode({"alg": "RS256", "kid": "k1"}, claims, key or self.key)
        code = uuid.uuid4().hex
        self.codes[code] = {"id_token": token, "challenge": query["code_challenge"][0]}
        return code


@pytest.fixture
def provider(monkeypatch):
    from services import sso

    fake = FakeProvider()
    monkeypatch.setattr(
        sso, "_client", lambda cacert="": httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    )
    monkeypatch.setattr(sso, "_metadata", {})
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("OIDC_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://testserver/api/v1/auth/sso/callback")
    monkeypatch.setenv("OIDC_NAME", "Acme")
    return fake


def _person(**claims) -> dict:
    tag = uuid.uuid4().hex[:8]
    return {"sub": f"id-{tag}", "email": f"Ana.{tag}@Acme.io", "given_name": "Ana", "family_name": "Lopez", **claims}


def _sign_in(client, provider: FakeProvider, **overrides) -> str:
    """The whole browser round trip; returns where the app lands."""
    started = client.get("/api/v1/auth/sso/start", follow_redirects=False)
    assert started.status_code == 302
    query = parse_qs(urlsplit(started.headers["location"]).query)
    code = provider.approve(started.headers["location"], **overrides)
    back = client.get(
        "/api/v1/auth/sso/callback", params={"code": code, "state": query["state"][0]}, follow_redirects=False
    )
    assert back.status_code == 302
    return back.headers["location"]


def test_the_sign_in_page_offers_what_is_set_up(client, provider, monkeypatch):
    # With SSO, the company's sign-in only; without it, passwords.
    assert client.get("/api/v1/auth/methods").json() == {"password": False, "sso": {"name": "Acme"}}
    monkeypatch.delenv("OIDC_ISSUER")
    assert client.get("/api/v1/auth/methods").json() == {"password": True, "sso": None}
    assert client.get("/api/v1/auth/sso/start", follow_redirects=False).status_code == 404


def test_a_first_sign_in_creates_the_account_and_starts_a_session(client, provider):
    provider.claims = _person()
    assert _sign_in(client, provider) == "/"

    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == provider.claims["email"].lower()
    assert (me["first_name"], me["last_name"]) == ("Ana", "Lopez")
    assert me["uses_password"] is False and me["permissions"] == []
    # No password to change.
    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": "anything", "new_password": "Something-new-1"},
        headers=csrf(client),
    )
    assert changed.status_code == 400

    # The same person later: the same account, even under a new email.
    client.post("/api/v1/auth/logout", headers=csrf(client))
    renamed = f"renamed-{uuid.uuid4().hex[:6]}@acme.io"
    assert _sign_in(client, provider, email=renamed) == "/"
    again = client.get("/api/v1/auth/me").json()
    assert again["id"] == me["id"] and again["email"] == renamed


def test_mapped_groups_give_and_take_roles(client, provider, make_user, monkeypatch):
    make_user(admin=True)  # another admin: this one's Admin role may go
    monkeypatch.setenv("OIDC_ROLE_MAP", "CN=Corpus Admins,OU=Groups,DC=acme=admin")
    provider.claims = _person(groups=["CN=Corpus Admins,OU=Groups,DC=acme", "Other"])
    _sign_in(client, provider)
    assert "users.list" in client.get("/api/v1/auth/me").json()["permissions"]

    client.post("/api/v1/auth/logout", headers=csrf(client))
    _sign_in(client, provider, groups=["Other"])
    assert client.get("/api/v1/auth/me").json()["permissions"] == []


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"aud": "another-app"}, "invalid"),
        ({"iss": "https://evil.test"}, "invalid"),
        ({"nonce": "replayed"}, "invalid"),
        ({"exp": 1}, "invalid"),
    ],
)
def test_tokens_that_do_not_check_out_are_refused(client, provider, change, error):
    provider.claims = _person()
    assert _sign_in(client, provider, **change) == f"/login?sso_error={error}"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_a_token_signed_by_another_key_is_refused(client, provider):
    provider.claims = _person()
    forged = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    assert _sign_in(client, provider, key=forged) == "/login?sso_error=invalid"


def test_an_answer_to_another_browsers_sign_in_is_refused(client, provider):
    provider.claims = _person()
    started = client.get("/api/v1/auth/sso/start", follow_redirects=False)
    code = provider.approve(started.headers["location"])
    back = client.get("/api/v1/auth/sso/callback", params={"code": code, "state": "guessed"}, follow_redirects=False)
    assert back.headers["location"] == "/login?sso_error=invalid"
    cancelled = client.get("/api/v1/auth/sso/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert cancelled.headers["location"] == "/login?sso_error=sso_denied"


def test_an_existing_account_is_taken_over_only_when_allowed(client, provider, make_user, monkeypatch):
    user_id, email, _ = make_user()
    provider.claims = _person(email=email)
    assert _sign_in(client, provider) == "/login?sso_error=sso_account_exists"

    monkeypatch.setenv("OIDC_LINK_BY_EMAIL", "on")
    assert _sign_in(client, provider) == "/"
    assert client.get("/api/v1/auth/me").json()["id"] == user_id


def test_a_disabled_account_cannot_sign_in(client, provider, make_user, monkeypatch):
    provider.claims = _person()
    _sign_in(client, provider)
    user_id = client.get("/api/v1/auth/me").json()["id"]
    client.post("/api/v1/auth/logout", headers=csrf(client))

    # An administrator disables the account (with a password, so SSO off meanwhile).
    with monkeypatch.context() as passwords:
        passwords.delenv("OIDC_ISSUER")
        _, admin_email, admin_password = make_user(admin=True)
        login(client, admin_email, admin_password)
        assert client.post(f"/api/v1/users/{user_id}/disable", headers=csrf(client)).status_code == 200
        client.post("/api/v1/auth/logout", headers=csrf(client))

    assert _sign_in(client, provider) == "/login?sso_error=account_disabled"


def test_with_sso_on_only_administrators_keep_their_password(client, provider, make_user):
    """Everyone else signs in through the company's provider; administrators
    keep a password to get in when the provider is down."""
    _, email, password = make_user(["documents.list"])
    refused = login(client, email, password)
    assert refused.status_code == 403 and refused.json()["code"] == "sso_required"
    # A wrong password stays a wrong password: nothing about who is an admin.
    assert login(client, email, "wrong-password").status_code == 401

    _, admin_email, admin_password = make_user(admin=True)
    assert login(client, admin_email, admin_password).status_code == 200
    assert client.get("/api/v1/auth/me").json()["uses_password"] is True
    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": admin_password, "new_password": "Another-pass-2"},
        headers=csrf(client),
    )
    assert changed.status_code == 204


def test_the_state_cookie_is_scoped_and_hidden_from_scripts(client, provider):
    started = client.get("/api/v1/auth/sso/start", follow_redirects=False)
    cookie = started.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "Path=/api/v1/auth/sso" in cookie
    assert "samesite=lax" in cookie.lower()
    # PKCE with S256, and nothing secret in the address.
    query = parse_qs(urlsplit(started.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"] and "client_secret" not in query
    assert json.dumps(query).find(SECRET) == -1


def test_production_reaches_the_provider_through_its_tunnel(client, provider, monkeypatch):
    """The backend has no route out: it dials sso-tunnel, while the Host
    header and the TLS name stay the provider's, so its certificate is
    still checked."""
    monkeypatch.setenv("OIDC_CONNECT", "sso-tunnel:443")
    provider.claims = _person()
    assert _sign_in(client, provider) == "/"
    assert provider.dialed and all(
        dialed == ("sso-tunnel", "idp.acme.test", "idp.acme.test") for dialed in provider.dialed
    )


def test_the_last_admin_keeps_the_role_when_the_group_drops_them(client, provider, monkeypatch):
    """A directory change must not leave Corpus without an administrator."""
    from conftest import run
    from sqlalchemy import func, select, update

    from database import AsyncSessionLocal
    from models import Role, User
    from models.rbac import role_users

    monkeypatch.setenv("OIDC_ROLE_MAP", "Admins=admin")
    provider.claims = _person(groups=["Admins"])
    _sign_in(client, provider)
    me = client.get("/api/v1/auth/me").json()

    async def set_other_admins(ids: list[int] | None) -> list[int]:
        """Disables the other active admins, or enables `ids` again."""
        async with AsyncSessionLocal() as session:
            if ids is None:
                ids = list(
                    await session.scalars(
                        select(User.id)
                        .join(role_users, role_users.c.user_id == User.id)
                        .join(Role, Role.id == role_users.c.role_id)
                        .where(Role.key == "admin", User.id != me["id"], User.disabled_at.is_(None))
                    )
                )
                await session.execute(update(User).where(User.id.in_(ids)).values(disabled_at=func.now()))
            else:
                await session.execute(update(User).where(User.id.in_(ids)).values(disabled_at=None))
            await session.commit()
            return ids

    others = run(set_other_admins(None))
    try:
        client.post("/api/v1/auth/logout", headers=csrf(client))
        _sign_in(client, provider, groups=[])
        assert "users.list" in client.get("/api/v1/auth/me").json()["permissions"]
    finally:
        run(set_other_admins(others))


def test_a_code_used_twice_asks_to_sign_in_again(client, provider):
    """The provider refuses a used code: that is an expired sign-in, not a
    provider that cannot be reached."""
    provider.claims = _person()
    started = client.get("/api/v1/auth/sso/start", follow_redirects=False)
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    code = provider.approve(started.headers["location"])
    first = client.get("/api/v1/auth/sso/callback", params={"code": code, "state": state}, follow_redirects=False)
    assert first.headers["location"] == "/"
    client.cookies.set("sso_state", started.cookies["sso_state"], path="/api/v1/auth/sso")
    again = client.get("/api/v1/auth/sso/callback", params={"code": code, "state": state}, follow_redirects=False)
    assert again.headers["location"] == "/login?sso_error=invalid"
