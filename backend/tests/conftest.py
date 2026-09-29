"""Test setup.

Needs only Postgres: start it with
    docker compose -f docker-compose.local.yml up -d postgres
Tests create a throwaway database next to the one in backend/.env, migrate
it, and drop it at the end. Qdrant, MinIO, RabbitMQ and Ollama are replaced
by fakes where a test touches them.

    cd backend && uv run pytest
"""

import asyncio
import os
import uuid
from collections.abc import Iterator

import pytest
from dotenv import dotenv_values

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
_TEST_DB = f"corpus_test_{uuid.uuid4().hex[:8]}"

# Before any app import: modules read the environment at import time.
os.environ.update(
    {
        "DB_USER": _ENV.get("DB_USER") or "postgres",
        "DB_PASSWORD": _ENV.get("DB_PASSWORD") or "",
        "DB_HOST": _ENV.get("DB_HOST") or "localhost",
        "DB_PORT": _ENV.get("DB_PORT") or "5432",
        "DB_NAME": _TEST_DB,
        "JWT_SECRET_KEY": "test-jwt-secret-" + "x" * 32,
        "DATA_ENCRYPTION_KEY": "test-encryption-key-" + "y" * 32,
        "APP_LANGUAGE": "en",
        "EMBEDING_MODEL": "multilingual-e5-small",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        "QDRANT_API_KEY": "test-qdrant-key-" + "z" * 32,
        "HF_HUB_OFFLINE": "1",
    }
)


async def _admin_execute(sql: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=_ENV.get("DB_NAME") or "postgres",
    )
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    try:
        asyncio.run(_admin_execute(f'CREATE DATABASE "{_TEST_DB}"'))
    except OSError as exc:
        pytest.exit(f"Postgres is not running ({exc}); start it with docker compose.", 2)
    from alembic import command
    from alembic.config import Config

    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "src", "alembic")
    )
    command.upgrade(config, "heads")

    # One event loop per test (TestClient, asyncio.run): pooled connections
    # would be bound to a closed loop.
    import database as db
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    db.AsyncSessionLocal.configure(
        bind=create_async_engine(db.DATABASE_URL, poolclass=NullPool)
    )
    asyncio.run(_seed_catalog())
    yield
    asyncio.run(_admin_execute(f'DROP DATABASE "{_TEST_DB}" WITH (FORCE)'))


async def _seed_catalog() -> None:
    from database import AsyncSessionLocal
    from seeders.permissions import seed_permissions
    from seeders.roles import seed_roles

    async with AsyncSessionLocal() as session:
        await seed_permissions(session)
        await seed_roles(session)
        await seed_permissions(session)
        await session.commit()


def run(coro):
    """Runs a coroutine from a sync test."""
    return asyncio.run(coro)


@pytest.fixture
def make_user():
    """Creates a user with a role holding `permissions`; returns
    (id, email, password)."""
    from database import AsyncSessionLocal
    from models import Permission, Role, User
    from services.password import hash_password
    from sqlalchemy import select

    async def create(permissions: list[str], admin: bool = False):
        tag = uuid.uuid4().hex[:8]
        email, password = f"user-{tag}@acme.io", f"Password-{tag}"
        async with AsyncSessionLocal() as session:
            if admin:
                role = await session.scalar(select(Role).where(Role.key == "admin"))
            else:
                perms = list(
                    await session.scalars(select(Permission).where(Permission.key.in_(permissions)))
                )
                role = Role(key=f"role-{tag}", name=f"Role {tag}", description="", permissions=perms)
                session.add(role)
            user = User(
                first_name="Test",
                last_name="User",
                email=email,
                password=hash_password(password),
                roles=[role],
            )
            session.add(user)
            await session.commit()
            return user.id, email, password

    return lambda permissions=(), admin=False: run(create(list(permissions), admin))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import main

    async def no_warm_up() -> None:  # no models in tests
        return None

    main.warm_up = no_warm_up
    with TestClient(main.app, base_url="https://testserver") as test_client:
        yield test_client


def login(client, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def csrf(client, name: str = "csrf_access_token") -> dict[str, str]:
    return {"X-CSRF-TOKEN": client.cookies.get(name) or ""}
