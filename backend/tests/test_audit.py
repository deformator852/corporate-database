"""Audit log: what is recorded, who may read it, user activity paging."""

from datetime import UTC, datetime, timedelta

from conftest import csrf, login, run


def test_actions_are_recorded_and_filtered(client, make_user):
    _, email, password = make_user(admin=True)
    login(client, email, "wrong-password")
    login(client, email, password)
    client.post("/api/v1/auth/logout", headers=csrf(client))
    login(client, email, password)
    items = client.get("/api/v1/audit", params={"q": email, "per_page": 100}).json()["items"]
    actions = {item["action"] for item in items}
    assert {"auth.login", "auth.login_failed", "auth.logout"} <= actions
    only = client.get("/api/v1/audit", params={"action": "auth.logout", "q": email}).json()
    assert only["total"] >= 1 and all(i["action"] == "auth.logout" for i in only["items"])


def test_audit_needs_permission(client, make_user):
    _, email, password = make_user(["documents.list"])
    login(client, email, password)
    assert client.get("/api/v1/audit").status_code == 403


def test_user_activity_pages_newest_first_without_gaps(client, make_user):
    from database import AsyncSessionLocal
    from models import AuditLog

    user_id, user_email, _ = make_user()
    _, email, password = make_user(admin=True)

    async def seed() -> None:
        base = datetime.now(UTC) - timedelta(days=3)
        async with AsyncSessionLocal() as session:
            for i in range(25):
                session.add(
                    AuditLog(
                        actor_id=user_id,
                        actor_email=user_email,
                        action="documents.upload",
                        details={},
                        # Three share a timestamp: ties must break by id.
                        created_at=base if i in (10, 11, 12) else base + timedelta(hours=i),
                    )
                )
            session.add(
                AuditLog(
                    actor_email=user_email, action="auth.login_failed", details={}, created_at=base - timedelta(days=1)
                )
            )
            await session.commit()

    run(seed())
    login(client, email, password)
    seen, before = [], None
    while True:
        params = {"limit": 7} | ({"before": before} if before else {})
        page = client.get(f"/api/v1/users/{user_id}/activity", params=params).json()
        seen += page["items"]
        before = page["next_cursor"]
        if before is None:
            break
    keys = [(e["created_at"], e["id"]) for e in seen]
    assert len(seen) == 26 and len({e["id"] for e in seen}) == 26
    assert keys == sorted(keys, reverse=True)
    assert seen[-1]["action"] == "auth.login_failed"


def test_user_page_needs_users_view(client, make_user):
    user_id, _, _ = make_user()
    _, email, password = make_user(["audit.list"])
    login(client, email, password)
    assert client.get(f"/api/v1/users/{user_id}").status_code == 403
    assert client.get(f"/api/v1/users/{user_id}/activity").status_code == 403
