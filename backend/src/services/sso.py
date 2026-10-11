"""Single sign-on with the company's identity provider (OpenID Connect,
authorization code flow with PKCE).

`start` sends the browser to the provider with a fresh state, nonce and PKCE
verifier, kept in a short signed cookie. `finish` takes the provider's code
back, exchanges it with the client secret, checks the ID token (signature by
the provider's keys, issuer, audience, expiry, nonce) and returns who
signed in. The provider's address is the configured issuer only: nothing in
the request chooses where this server connects.
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode, urlsplit

import httpx
from joserfc import jws, jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, OctKey

from exceptions import AppError
from settings import OidcConfig

STATE_COOKIE = "sso_state"
STATE_COOKIE_PATH = "/api/v1/auth/sso"
STATE_SECONDS = 10 * 60
_METADATA_SECONDS = 60 * 60
_TIMEOUT = httpx.Timeout(10.0)
# Asymmetric only: a shared-secret signature would be checkable with keys
# the provider publishes to everyone.
_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]


@dataclass(frozen=True, slots=True)
class SsoIdentity:
    # "ISSUER SUBJECT": the provider's unchanging id of the person.
    subject: str
    email: str | None
    first_name: str
    last_name: str
    groups: list[str]


def _client(cacert: str = "") -> httpx.AsyncClient:
    """Tests replace it with one answering as a provider."""
    return httpx.AsyncClient(timeout=_TIMEOUT, verify=cacert or True)


_metadata: dict[str, tuple[float, dict]] = {}


async def _provider(config: OidcConfig) -> dict:
    """The provider's discovery document, cached for an hour."""
    cached = _metadata.get(config.issuer)
    if cached and time.monotonic() - cached[0] < _METADATA_SECONDS:
        return cached[1]
    document = await _get_json(config, f"{config.issuer}/.well-known/openid-configuration")
    if str(document.get("issuer", "")).rstrip("/") != config.issuer:
        raise AppError("misconfigured", "The SSO provider names another issuer.", status_code=502)
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not str(document.get(field, "")).startswith("https://"):
            raise AppError("misconfigured", "The SSO provider's discovery document is incomplete.", status_code=502)
    issuer_host = urlsplit(config.issuer).netloc
    if config.connect and any(urlsplit(document[f]).netloc != issuer_host for f in ("token_endpoint", "jwks_uri")):
        # The tunnel leads to the issuer's host only.
        raise AppError("misconfigured", "The SSO provider's endpoints are on another host than the issuer.", 502)
    _metadata[config.issuer] = (time.monotonic(), document)
    return document


async def _get_json(config: OidcConfig, url: str, *, method: str = "GET", **kwargs) -> dict:
    headers = dict(kwargs.pop("headers", {}))
    extensions = {}
    if config.connect:
        # Dial the tunnel, but speak to the provider: Host header and TLS name.
        target = urlsplit(url)
        url = target._replace(netloc=config.connect).geturl()
        headers["Host"] = target.netloc
        extensions["sni_hostname"] = target.hostname
    try:
        async with _client(config.cacert) as client:
            response = await client.request(method, url, headers=headers, extensions=extensions, **kwargs)
            if 400 <= response.status_code < 500:
                # Reached, but refused: a code used twice or too late (a
                # double click, a slow return). Signing in again works.
                raise AppError("invalid", "The sign-in expired. Try again.", status_code=400)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError("unavailable", "Could not reach the SSO provider.", status_code=503) from exc


def _secret_key(secret: str) -> OctKey:
    return OctKey.import_key(hashlib.sha256(b"sso-state:" + secret.encode()).digest())


async def start(config: OidcConfig, secret: str) -> tuple[str, str]:
    """The provider's sign-in address, and the cookie value that must come
    back with the answer."""
    provider = await _provider(config)
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    payload = {"state": state, "nonce": nonce, "verifier": verifier, "exp": int(time.time()) + STATE_SECONDS}
    cookie = jws.serialize_compact({"alg": "HS256"}, json.dumps(payload), _secret_key(secret))
    return f"{provider['authorization_endpoint']}?{query}", cookie


def _pending(cookie: str | None, state: str, secret: str) -> dict:
    """The sign-in this browser started; refuses an answer to another one."""
    if not cookie:
        raise AppError("invalid", "The sign-in expired. Try again.", status_code=400)
    try:
        payload = json.loads(jws.deserialize_compact(cookie, _secret_key(secret), algorithms=["HS256"]).payload)
    except (JoseError, ValueError) as exc:
        raise AppError("invalid", "The sign-in expired. Try again.", status_code=400) from exc
    if payload.get("exp", 0) < time.time() or not secrets.compare_digest(str(payload.get("state")), state):
        raise AppError("invalid", "The sign-in expired. Try again.", status_code=400)
    return payload


async def finish(config: OidcConfig, secret: str, *, code: str, state: str, cookie: str | None) -> SsoIdentity:
    """Who signed in at the provider."""
    pending = _pending(cookie, state, secret)
    provider = await _provider(config)
    tokens = await _get_json(
        config,
        provider["token_endpoint"],
        method="POST",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code_verifier": pending["verifier"],
        },
        headers={"Accept": "application/json"},
    )
    keys = KeySet.import_key_set(cast(Any, await _get_json(config, provider["jwks_uri"])))
    try:
        token = jwt.decode(str(tokens.get("id_token", "")), keys, algorithms=_ALGORITHMS)
        jwt.JWTClaimsRegistry(
            leeway=60,
            iss={"essential": True, "value": provider["issuer"]},
            aud={"essential": True, "value": config.client_id},
            sub={"essential": True},
            exp={"essential": True},
            nonce={"essential": True, "value": pending["nonce"]},
        ).validate(token.claims)
    except (JoseError, ValueError) as exc:
        raise AppError("invalid", "The SSO provider's answer could not be verified.", status_code=400) from exc
    return _identity(config, token.claims)


def _identity(config: OidcConfig, claims: dict) -> SsoIdentity:
    email = next(
        (
            str(value).strip().lower()
            for value in (claims.get("email"), claims.get("preferred_username"))
            if isinstance(value, str) and "@" in value
        ),
        None,
    )
    full = str(claims.get("name") or "").split()
    fallback = (email or str(claims["sub"])).split("@")[0]
    groups = claims.get(config.groups_claim) or []
    return SsoIdentity(
        subject=f"{config.issuer} {claims['sub']}",
        email=email,
        first_name=_name(claims.get("given_name") or (full[0] if full else None), fallback),
        last_name=_name(claims.get("family_name") or (" ".join(full[1:]) if len(full) > 1 else None), fallback),
        groups=[str(group) for group in groups] if isinstance(groups, list) else [],
    )


def _name(value: object, fallback: str) -> str:
    """2-100 characters, as every account's names."""
    text = str(value).strip() if value else ""
    if len(text) < 2:
        text = fallback
    return text[:100].ljust(2, "_")
