import secrets

from rich.console import Console
from rich.panel import Panel

from ..env import ENV_PATH, env_value, upsert_env

_DEFAULT = "minioadmin"


def _missing(value: str | None, *weak: str | None) -> bool:
    return not value or value == _DEFAULT or value in weak


class StorageStep:
    title = "Object storage credentials"

    def run(self, console: Console) -> None:
        root_user = env_value(ENV_PATH, "MINIO_ROOT_USER")
        root_password = env_value(ENV_PATH, "MINIO_ROOT_PASSWORD")
        app_user = env_value(ENV_PATH, "MINIO_ACCESS_KEY")
        app_secret = env_value(ENV_PATH, "MINIO_SECRET_KEY")

        written: list[str] = []
        if _missing(root_user):
            root_user = "minio-root"
            written.append("MINIO_ROOT_USER")
        if _missing(root_password):
            root_password = secrets.token_urlsafe(24)
            written.append("MINIO_ROOT_PASSWORD")
        # The app must never run with the root account.
        if _missing(app_user, root_user):
            app_user = "corporate-app"
            written.append("MINIO_ACCESS_KEY")
        if _missing(app_secret, root_password):
            app_secret = secrets.token_urlsafe(24)
            written.append("MINIO_SECRET_KEY")

        if not written:
            console.print("MinIO credentials are already set.")
            return
        for key, value in (
            ("MINIO_ROOT_USER", root_user),
            ("MINIO_ROOT_PASSWORD", root_password),
            ("MINIO_ACCESS_KEY", app_user),
            ("MINIO_SECRET_KEY", app_secret),
        ):
            if key in written:
                upsert_env(ENV_PATH, key, value)
        console.print(f"Generated {', '.join(written)} in {ENV_PATH}")
        console.print(
            Panel(
                "Apply the new credentials before starting the backend:\n"
                "docker compose -f docker-compose.local.yml up -d minio minio-init\n\n"
                "Stored files are kept.",
                title="Restart MinIO",
                style="yellow",
            )
        )
