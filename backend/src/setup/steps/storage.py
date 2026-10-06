from rich.console import Console
from rich.panel import Panel

from ..env import ENV_PATH, env_value, random_secret, upsert_env

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

        written: dict[str, str] = {}
        if _missing(root_user):
            root_user = written["MINIO_ROOT_USER"] = "minio-root"
        if _missing(root_password):
            root_password = written["MINIO_ROOT_PASSWORD"] = random_secret(24)
        # The app must never run with the root account.
        if _missing(app_user, root_user):
            written["MINIO_ACCESS_KEY"] = "corporate-app"
        if _missing(app_secret, root_password):
            written["MINIO_SECRET_KEY"] = random_secret(24)

        if not written:
            console.print("MinIO credentials are already set.")
            return
        for key, value in written.items():
            upsert_env(ENV_PATH, key, value)
        console.print(f"Generated {', '.join(written)} in {ENV_PATH}")
        console.print(
            Panel(
                "Apply the new credentials before starting the backend:\n"
                "docker compose --env-file backend/.env -f docker-compose.local.yml up -d minio minio-init\n\n"
                "Stored files are kept.",
                title="Restart MinIO",
                style="yellow",
            )
        )
