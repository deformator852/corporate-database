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
```

Put the `min_score` it prints into the model's entry in `src/settings.py`.

## Changing settings

```sh
cd backend
uv run configure        # AI model, chat limits, chunk size
uv run setup key        # fingerprint of the encryption key
```

To deploy to a server, see
[Deploying Corpus on a company server](../documentations/deployment.md).
