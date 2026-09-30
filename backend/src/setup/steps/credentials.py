from rich.console import Console
from rich.panel import Panel

from ..env import ENV_PATH, env_value, random_secret, upsert_env
from ..key import confirm_backup

# key → minimum length; shorter values (e.g. "password") are replaced.
_SECRETS = {
    "JWT_SECRET_KEY": 32,  # HS256 wants 256+ bits
    "DB_PASSWORD": 16,
    "RABBITMQ_PASSWORD": 16,
    "QDRANT_API_KEY": 32,
    # Encrypts files, document text and chats at rest. Never replaced here:
    # a new key would make stored data unreadable (`uv run setup key rotate`).
    "DATA_ENCRYPTION_KEY": 32,
}
# Names are only filled when empty: renaming breaks existing data.
_NAMES = {
    "DB_USER": "corporate",
    "DB_NAME": "corporate",
    "RABBITMQ_USER": "corporate",
}


class SecretsStep:
    title = "Secrets"

    def run(self, console: Console) -> None:
        written: list[str] = []
        for key, default in _NAMES.items():
            if not env_value(ENV_PATH, key):
                upsert_env(ENV_PATH, key, default)
                written.append(key)
        for key, min_length in _SECRETS.items():
            if len(env_value(ENV_PATH, key) or "") < min_length:
                upsert_env(ENV_PATH, key, random_secret())
                written.append(key)

        if not written:
            console.print("Secrets are already set.")
            return
        console.print(f"Generated {', '.join(written)} in {ENV_PATH}")
        notes = [
            "Apply them before starting the backend:",
            "docker compose --env-file backend/.env -f docker-compose.local.yml up -d",
            "",
            "Postgres and RabbitMQ pick up a new password on restart; data is kept.",
        ]
        if "JWT_SECRET_KEY" in written:
            notes.append("A new JWT secret signs everyone out.")
        console.print(Panel("\n".join(notes), title="Restart services", style="yellow"))
        if "DATA_ENCRYPTION_KEY" in written:
            confirm_backup(console, env_value(ENV_PATH, "DATA_ENCRYPTION_KEY") or "")
