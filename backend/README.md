# Corpus backend

The backend is a FastAPI application with a Celery worker that processes
uploaded documents. This guide shows you how to run it on a development
machine.

## Prerequisites

* [uv](https://docs.astral.sh/uv/)
* Docker with Docker Compose v2, for Postgres, Qdrant, RabbitMQ, MinIO and
  Ollama

## Running the backend

1. Generate `backend/.env`. The setup creates the secrets and asks for the
   system language, the AI models and the chat limits.

   ```sh
   cd backend
   uv run setup
   ```

2. Start the services. Run this from the repository root:

   ```sh
   docker compose --env-file backend/.env -f docker-compose.local.yml up -d
   ```

3. Create the database tables and the default roles and permissions:

   ```sh
   cd backend
   uv run alembic upgrade heads
   cd src && uv run python -m seeders.run
   ```

4. Create an administrator. The command prints the password once.

   ```sh
   cd backend/src
   uv run python -m maintenance.create_admin ADMIN-EMAIL
   ```

5. Start the API and the worker in two terminals, both from `backend/`:

   ```sh
   uv run uvicorn src.main:app --reload
   ```

   ```sh
   uv run celery -A worker worker --loglevel=info
   ```

The API listens on `http://127.0.0.1:8000`. Settings are read when a process
starts: after you change `.env` or run `uv run configure`, restart the API and
the worker.

## Running the tests

The tests need only the local Postgres from step 2. Each run creates and drops
its own database, and the other services are replaced by fakes.

```sh
cd backend
uv run pytest
```

## Evaluating search and sources

`evals/` holds company documents and questions in English, Spanish and French,
including questions with no answer in them. Run these after changing the
embedding model, the AI model, the chat prompt or the cleanup rules:

```sh
cd backend
uv run python evals/search_relevance.py MODEL   # calibrates min_score of an embedding model
uv run python evals/chat_sources.py LANGUAGE    # checks the sources the chat shows (needs Ollama)
uv run python evals/text_cleanup.py LANGUAGE    # what cleanup rules give search on noisy documents
uv run python evals/chunk_context.py MODEL      # what the header row gives search in table chunks
uv run python evals/chunking.py MODEL           # cutting at sections against cutting by size
uv run python evals/keyword_search.py MODEL     # keyword search for names and codes in tables
```

Put the `min_score` it prints into the model's entry in `src/settings.py`.

## Changing settings

```sh
cd backend
uv run configure        # AI model, chat limits, chunk size
uv run setup key        # fingerprint of the encryption key
```

To use another embedding model once documents exist:

```sh
cd backend
uv run switch-embedding-model MODEL   # for example bge-m3; without MODEL it lists them
```

It stops the backend and the worker running from this folder, rebuilds the
search index, writes `EMBEDDING_MODEL` to `.env` and queues every document.
Start the backend and the worker again and the worker embeds them with the
new model. Run it with the current model to rebuild the index, for example
after changing the chunk size.

## Testing single sign-on locally

A test identity provider (Keycloak) runs in Docker when you ask for it. Its
realm `corpus` comes from `dev/keycloak/corpus-realm.json`:

| User | Password | Group |
|---|---|---|
| `ana` | `ana-password-1` | Corpus Admins |
| `bob` | `bob-password-1` | Legal |

These are test values; never use them anywhere else.

1. Start Keycloak from the repository root. The first start makes a
   self-signed certificate in `dev/keycloak/certs/`.

   ```sh
   docker compose --env-file backend/.env -f docker-compose.local.yml --profile sso up -d keycloak
   ```

2. Open `https://localhost:8443` once and accept the certificate warning.
3. In `backend/`, run `uv run configure`. At the Sign-in step answer yes and
   enter:

   | Question | Answer |
   |---|---|
   | Issuer address | `https://localhost:8443/realms/corpus` |
   | CA file | `../dev/keycloak/certs/ca.pem` |
   | Client ID | `corpus` |
   | Client secret | `corpus-local-secret-0123456789` |
   | Callback address | `http://localhost:5173/api/v1/auth/sso/callback` |
   | Button name | `Keycloak` |
   | Group to role map | `Corpus Admins=admin` |

4. Restart the backend and the frontend development server, open
   `http://localhost:5173/login` and select **Sign in with Keycloak**.

Manage users and groups in the Keycloak admin console,
`https://localhost:8443/admin` (`admin` / `admin`). Keycloak keeps changes
until its container is removed; then the realm loads from the file again.

To stop it, run `docker compose -f docker-compose.local.yml --profile sso
stop keycloak`. To turn single sign-on off, run `uv run configure` and answer
no at the Sign-in step.

## Testing the Vault key store locally

A test HashiCorp Vault starts with the other development services, set up as a
company's Vault administrator would (`dev/vault/start.sh`): KV v2 at
`secret`, an AppRole `corpus` that may only read `secret/data/corpus`, and a
token that may write it. These are test values; never use them anywhere else.

Its data is on the `vault_data` Docker volume: a key moved there survives
restarts, and is lost with the volume. Back up the key first:

```sh
cd backend && uv run setup key --show
```

1. Start the development services from the repository root, Vault included:

   ```sh
   docker compose --env-file backend/.env -f docker-compose.local.yml up -d
   ```

2. In `backend/`, run `uv run configure`. At the Encryption key storage step
   choose HashiCorp Vault and enter:

   | Question | Answer |
   |---|---|
   | CA file | Enter (none: the test Vault uses plain HTTP) |
   | Vault address | `http://localhost:8200` |
   | AppRole role_id | `corpus-local-role-id` |
   | AppRole secret_id | `corpus-local-secret-id` (hidden while you type) |
   | KV v2 mount | Enter (`secret`) |
   | Secret path | Enter (`corpus`) |
   | Vault token | `corpus-local-admin-token` (hidden while you type) |

   It writes the key to Vault, checks the AppRole reads it back and removes
   it from `.env`.

3. Restart the backend and the worker: they now read the key from Vault.

The production stack on the same machine reads the same `backend/.env`; it
cannot reach a Vault at `localhost` from its containers, so it does not
start while the key is there. To move the key back, run `uv run configure`
and choose the `.env` file. The Vault UI is at `http://localhost:8200`.

To deploy to a server, see
[Deploying Corpus on a company server](../documentations/deployment.md).
