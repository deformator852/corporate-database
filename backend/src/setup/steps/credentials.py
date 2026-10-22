from rich.console import Console

from ..env import ENV_PATH, env_value, random_secret, upsert_env
from ..key import confirm_backup, in_vault

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
        new_key: str | None = None
        for key, default in _NAMES.items():
            if not env_value(ENV_PATH, key):
                upsert_env(ENV_PATH, key, default)
                written.append(key)
        for key, min_length in _SECRETS.items():
            if key == "DATA_ENCRYPTION_KEY" and in_vault():
                continue  # kept in Vault: a key here would be a second, wrong one
            if len(env_value(ENV_PATH, key) or "") < min_length:
                if key == "DATA_ENCRYPTION_KEY":
                    # Written only once its backup is confirmed: setup stopped
                    # at the prompt makes a new key and asks again next time.
                    new_key = random_secret()
                else:
                    upsert_env(ENV_PATH, key, random_secret())
                written.append(key)

        if not written:
            console.print("Secrets are already set.")
            return
        console.print(f"Generated {', '.join(written)} in {ENV_PATH}")
        if new_key:
            confirm_backup(console, new_key)
            upsert_env(ENV_PATH, "DATA_ENCRYPTION_KEY", new_key)
