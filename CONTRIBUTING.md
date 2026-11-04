# Contributing to Archfold

This guide shows you how to run the checks and what a change must include. To
set up a development environment, see [README.md](README.md) and the
[backend](backend/README.md) and [frontend](frontend/README.md) guides.

To report a vulnerability, follow [SECURITY.md](SECURITY.md), not this guide.

## Before you start

Open an issue before a large change, so you do not build something that cannot
be merged. Small fixes can go straight to a pull request.

## Run the checks

A pull request must pass all of these.

Backend, which needs only the local Postgres:

```sh
docker compose --env-file backend/.env -f docker-compose.local.yml up -d postgres
cd backend
uv run ruff check
uv run ruff format --check
uv run ty check src
uv run pytest
```

Frontend:

```sh
cd frontend
npx tsc -b
npx oxlint src
npx vitest run
```

## What a change must include

* **A test.** Every feature has one. Test through the HTTP API, the WebSocket,
  the command line or the rendered interface, not through internals. Frontend
  tests query by role and label, never by CSS class.
* **Translations.** Add every new user-facing message in English, Spanish and
  French.
* **Colors from the theme.** Use daisyUI's tokens, such as `bg-base-100` or
  `text-error`, so that every theme works. Do not use raw colors.

## Rules that protect users

* Never log or store unencrypted document text, chat content or secrets.
* Never add a runtime dependency on the internet, such as telemetry or update
  checks. Archfold runs on the company's own servers.
* Do not add files under `backend/src/custom/` or `frontend/src/custom/`. Those
  folders belong to the people who install Archfold.

## License

By submitting a contribution, you agree that it is licensed under the
[Apache License 2.0](LICENSE), as section 5 of the license says.
