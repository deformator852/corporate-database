import secrets

from rich.console import Console
from rich.panel import Panel

from ..env import ENV_PATH, env_value, upsert_env

# key → minimum length; shorter values (e.g. "password") are replaced.
_SECRETS = {
    "JWT_SECRET_KEY": 32,  # HS256 wants 256+ bits
    "DB_PASSWORD": 16,
    "RABBITMQ_PASSWORD": 16,
    "QDRANT_API_KEY": 32,
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
                upsert_env(ENV_PATH, key, secrets.token_urlsafe(32))
                written.append(key)

        if not written:
            console.print("Secrets are already set.")
            return
        console.print(f"Generated {', '.join(written)} in {ENV_PATH}")
        notes = [
            "Apply them before starting the backend:",
            "docker compose -f docker-compose.local.yml up -d",
            "",
            "Postgres and RabbitMQ pick up a new password on restart; data is kept.",
        ]
        if "JWT_SECRET_KEY" in written:
            notes.append("A new JWT secret signs everyone out.")
        console.print(Panel("\n".join(notes), title="Restart services", style="yellow"))
