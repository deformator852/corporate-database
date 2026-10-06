"""Managing users, roles, permissions and notifications through the API."""

import uuid

import pytest
from conftest import csrf, login, run

ADMIN_PAGE = ["users.list", "users.view", "users.create", "users.update", "users.delete"]


def _payload(email: str, **extra) -> dict:
    return {"first_name": "Ana", "last_name": "López", "email": email, "role_keys": [], **extra}


def _email() -> str:
    return f"new-{uuid.uuid4().hex[:8]}@acme.io"


# Users


def test_admin_creates_updates_and_deletes_a_user(client, make_user):
    _, email, password = make_user(admin=True)
    login(client, email, password)
    new_email = _email()

    created = client.post(
        "/api/v1/users", headers=csrf(client), json=_payload(new_email.upper(), password="Initial-pass-1")
    )
    assert created.status_code == 201
    user = created.json()
    assert user["email"] == new_email and user["disabled"] is False  # normalized
    assert (
        login(client.__class__(client.app, base_url="https://testserver"), new_email, "Initial-pass-1").status_code
        == 200
    )

    updated = client.patch(
        f"/api/v1/users/{user['id']}",
        headers=csrf(client),
        json=_payload(new_email, first_name="  Anabel ", role_keys=["admin"]),
    )
    assert updated.status_code == 200
    assert updated.json()["first_name"] == "Anabel" and updated.json()["roles"][0]["key"] == "admin"

    assert client.delete(f"/api/v1/users/{user['id']}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/v1/users/{user['id']}").status_code == 404
    actions = [e["action"] for e in client.get("/api/v1/audit", params={"q": new_email}).json()["items"]]
    assert {"users.create", "users.update", "users.delete"} <= set(actions)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"first_name": " A "}, "at least 2"),
        ({"password": "short"}, "at least 8"),
        ({"password": "п" * 40}, "too long"),
        ({"role_keys": ["no.such.role"]}, "roles do not exist"),
    ],
)
def test_invalid_user_input_is_explained(client, make_user, change, message):
    _, email, password = make_user(admin=True)
    login(client, email, password)
    body = _payload(_email(), password="Valid-pass-1") | change

    response = client.post("/api/v1/users", headers=csrf(client), json=body)

    assert response.status_code in {400, 422}
    assert message in response.json()["message"]


def test_email_must_be_unique(client, make_user):
    _, email, password = make_user(admin=True)
    _, taken, _ = make_user()
    login(client, email, password)
    response = client.post("/api/v1/users", headers=csrf(client), json=_payload(taken, password="Valid-pass-1"))
    assert response.status_code == 409 and response.json()["message"] == "A user with this email already exists"


def test_cannot_delete_yourself_or_the_last_admin(client, make_user):
    admin_id, email, password = make_user(admin=True)
    login(client, email, password)
    assert client.delete(f"/api/v1/users/{admin_id}", headers=csrf(client)).status_code == 409

    from services.user import UserService

    async def only_admin() -> set[int]:
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            return await UserService(session).admin_ids()

    others = run(only_admin()) - {admin_id}
    _, manager_email, manager_password = make_user(ADMIN_PAGE + ["users.disable"])
    # Leave exactly one active admin: disable every other one.
    login(client, email, password)
    for other in others:
        client.post(f"/api/v1/users/{other}/disable", headers=csrf(client))
    listed = client.get("/api/v1/users", params={"per_page": 100}).json()["items"]
    assert next(u for u in listed if u["id"] == admin_id)["is_last_admin"] is True
    removed = client.patch(f"/api/v1/users/{admin_id}", headers=csrf(client), json=_payload(email, role_keys=[]))
    assert removed.status_code == 409
    for other in others:
        client.post(f"/api/v1/users/{other}/enable", headers=csrf(client))


def test_user_list_pages(client, make_user):
    _, email, password = make_user(["users.list"])
    for _ in range(3):
        make_user()
    login(client, email, password)
    first = client.get("/api/v1/users", params={"per_page": 2}).json()
    second = client.get("/api/v1/users", params={"per_page": 2, "page": 2}).json()
    assert len(first["items"]) == 2 and first["pages"] == (first["total"] + 1) // 2
    assert {u["id"] for u in first["items"]}.isdisjoint(u["id"] for u in second["items"])


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("get", "/api/v1/users", "users.list"),
        ("post", "/api/v1/users", "users.create"),
        ("patch", "/api/v1/users/1", "users.update"),
        ("delete", "/api/v1/users/1", "users.delete"),
        ("post", "/api/v1/users/1/disable", "users.disable"),
        ("get", "/api/v1/roles", "roles.list"),
        ("post", "/api/v1/roles", "roles.create"),
        ("patch", "/api/v1/roles/x", "roles.update"),
        ("delete", "/api/v1/roles/x", "roles.delete"),
        ("get", "/api/v1/permissions", "permissions.list"),
        ("get", "/api/v1/system/status", "system.view"),
        ("get", "/api/v1/audit", "audit.list"),
        ("get", "/api/v1/documents", "documents.list"),
    ],
)
def test_every_management_route_needs_its_permission(client, make_user, method, path, permission):
    _, email, password = make_user([])
    login(client, email, password)
    response = getattr(client, method)(
        path, headers=csrf(client), **({"json": {}} if method in {"post", "patch"} else {})
    )
    assert response.status_code == 403, permission


def test_routes_need_a_session(client):
    for path in ("/api/v1/auth/me", "/api/v1/users", "/api/v1/notifications", "/api/v1/chat/conversations"):
        assert client.get(path).status_code == 401


def test_me_lists_the_users_permissions(client, make_user):
    _, email, password = make_user(["documents.list", "audit.list"])
    login(client, email, password)
    me = client.get("/api/v1/auth/me").json()
    assert set(me["permissions"]) == {"documents.list", "audit.list"}


# Roles and permissions


def test_role_lifecycle(client, make_user):
    _, email, password = make_user(admin=True)
    login(client, email, password)
    # 8 hex characters: make_user's roles ("role-<8 hex>") must not match the
    # search below by chance, as 4 did about once in a hundred runs.
    name = f"Legal team {uuid.uuid4().hex[:8]}"

    created = client.post(
        "/api/v1/roles",
        headers=csrf(client),
        json={"name": name, "description": " Contracts ", "permission_keys": ["documents.list"]},
    )
    assert created.status_code == 201
    role = created.json()
    assert role["key"] == name.lower().replace(" ", ".") and role["description"] == "Contracts"

    found = client.get("/api/v1/roles", params={"q": name[-8:]}).json()["items"]
    assert [r["key"] for r in found] == [role["key"]]
    updated = client.patch(
        f"/api/v1/roles/{role['key']}",
        headers=csrf(client),
        json={"description": "", "permission_keys": ["documents.list", "documents.restricted"]},
    )
    assert {p["key"] for p in updated.json()["permissions"]} == {"documents.list", "documents.restricted"}
    # The audit log keeps readable names (they never change after creation).
    entry = client.get("/api/v1/audit", params={"action": "roles.update", "q": name}).json()["items"][0]
    assert entry["details"]["permissions"] == ["List documents", "Restricted documents"]
    duplicate = client.post("/api/v1/roles", headers=csrf(client), json={"name": name})
    assert duplicate.status_code == 409

    assert client.delete(f"/api/v1/roles/{role['key']}", headers=csrf(client)).status_code == 204
    assert client.delete(f"/api/v1/roles/{role['key']}", headers=csrf(client)).status_code == 404


def test_admin_role_cannot_be_deleted_or_trimmed(client, make_user):
    _, email, password = make_user(admin=True)
    login(client, email, password)
    assert client.delete("/api/v1/roles/admin", headers=csrf(client)).status_code == 409
    trimmed = client.patch("/api/v1/roles/admin", headers=csrf(client), json={"permission_keys": ["users.list"]})
    assert trimmed.status_code == 409


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"name": "1st team"}, "start with a letter"),
        ({"name": "!!"}, "at least 2"),
        ({"name": "Ops", "permission_keys": ["no.such"]}, "permissions do not exist"),
    ],
)
def test_invalid_roles_are_explained(client, make_user, body, message):
    _, email, password = make_user(admin=True)
    login(client, email, password)
    response = client.post("/api/v1/roles", headers=csrf(client), json=body)
    assert response.status_code in {400, 422} and message in response.json()["message"]


def test_permission_catalog_is_searchable(client, make_user):
    _, email, password = make_user(["permissions.list"])
    login(client, email, password)
    everything = client.get("/api/v1/permissions", params={"per_page": 100}).json()
    keys = {p["key"] for p in everything["items"]}
    assert {"users.disable", "system.view", "audit.list", "documents.secret"} <= keys
    found = client.get("/api/v1/permissions", params={"q": "audit"}).json()["items"]
    assert [p["key"] for p in found] == ["audit.list"]
    assert client.get("/api/v1/permissions", params={"q": "%"}).json()["total"] == 0  # LIKE is escaped


# Notifications


def _notify(user_id: int, message: str) -> int:
    from database import AsyncSessionLocal
    from models.notification import NotificationType
    from services.notifications.notification import NotificationService

    async def create() -> int:
        async with AsyncSessionLocal() as session:
            note = await NotificationService(session).create(user_id, NotificationType.DOCUMENT_COMPLETED, message)
            await session.commit()
            return note.id

    return run(create())


def test_notifications_can_be_read_dismissed_and_cleared(client, make_user):
    user_id, email, password = make_user()
    first, second, third = (_notify(user_id, f"Note {i}") for i in range(3))
    login(client, email, password)

    listed = client.get("/api/v1/notifications").json()
    assert [n["id"] for n in listed["items"]] == [third, second, first] and listed["unread_count"] == 3

    assert (
        client.post("/api/v1/notifications/read", headers=csrf(client), json={"ids": [first, second]}).status_code
        == 204
    )
    assert client.get("/api/v1/notifications").json()["unread_count"] == 1
    assert client.delete(f"/api/v1/notifications/{third}", headers=csrf(client)).status_code == 204
    assert [n["id"] for n in client.get("/api/v1/notifications").json()["items"]] == [second, first]
    assert client.delete("/api/v1/notifications", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/notifications").json()["total"] == 0


def test_notification_reaches_only_its_owner_live(client, make_user, infra):
    from services.notifications.hub import dispatch_notification

    owner_id, email, password = make_user()
    other_id, _, _ = make_user()
    login(client, email, password)
    headers = {"origin": "https://testserver", "cookie": f"my_token={client.cookies.get('my_token')}"}
    with client.websocket_connect("/api/v1/notifications/ws", headers=headers) as socket:
        client.portal.call(dispatch_notification, {"user_id": other_id, "message": "not yours"})
        client.portal.call(dispatch_notification, {"user_id": owner_id, "message": "yours"})
        assert socket.receive_json()["message"] == "yours"
