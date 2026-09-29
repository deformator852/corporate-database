"""Users with users.* or roles.* rights must not become admins."""

from conftest import csrf, login, run

MANAGER = ["users.list", "users.create", "users.update", "roles.list", "roles.update"]


def _user_payload(email: str, roles: list[str], password: str | None = None) -> dict:
    body = {"first_name": "Test", "last_name": "User", "email": email, "role_keys": roles}
    if password:
        body["password"] = password
    return body


def test_cannot_grant_self_admin(client, make_user):
    user_id, email, password = make_user(MANAGER)
    login(client, email, password)
    response = client.patch(
        f"/api/v1/users/{user_id}", headers=csrf(client), json=_user_payload(email, ["admin"])
    )
    assert response.status_code == 403


def test_cannot_reset_admin_password(client, make_user):
    admin_id, admin_email, _ = make_user(admin=True)
    _, email, password = make_user(MANAGER)
    login(client, email, password)
    response = client.patch(
        f"/api/v1/users/{admin_id}",
        headers=csrf(client),
        json=_user_payload(admin_email, ["admin"], "Hijacked-password-1"),
    )
    assert response.status_code == 403


def test_cannot_create_admin(client, make_user):
    _, email, password = make_user(MANAGER)
    login(client, email, password)
    response = client.post(
        "/api/v1/users",
        headers=csrf(client),
        json=_user_payload("evil@acme.io", ["admin"], "Evil-password-1"),
    )
    assert response.status_code == 403


def test_role_cannot_gain_permission_actor_lacks(client, make_user):
    _, email, password = make_user(MANAGER)
    login(client, email, password)
    roles = client.get("/api/v1/roles", params={"per_page": 100}).json()["items"]
    own = next(r for r in roles if r["key"].startswith("role-"))
    response = client.patch(
        f"/api/v1/roles/{own['key']}",
        headers=csrf(client),
        json={"description": "", "permission_keys": MANAGER + ["documents.secret"]},
    )
    assert response.status_code == 403


def test_admin_role_keeps_every_permission(client, make_user):
    _, email, password = make_user(admin=True)
    login(client, email, password)
    response = client.patch(
        "/api/v1/roles/admin", headers=csrf(client), json={"description": "x", "permission_keys": []}
    )
    assert response.status_code == 409


def test_seeders_keep_roles_created_in_the_ui():
    from database import AsyncSessionLocal
    from models import Role
    from seeders.permissions import seed_permissions
    from seeders.roles import seed_roles
    from sqlalchemy import select

    async def scenario() -> bool:
        async with AsyncSessionLocal() as session:
            session.add(Role(key="auditors-ui", name="Auditors UI", description="", permissions=[]))
            await session.commit()
        async with AsyncSessionLocal() as session:
            await seed_permissions(session)
            await seed_roles(session)
            await seed_permissions(session)
            await session.commit()
        async with AsyncSessionLocal() as session:
            return await session.scalar(select(Role.id).where(Role.key == "auditors-ui")) is not None

    assert run(scenario())
