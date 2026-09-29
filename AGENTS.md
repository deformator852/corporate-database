# Agent

On coding tasks, read and follow:

- ~/.agents/skills/ponytail/SKILL.md

On react hook form work, also:

- ~/.agents/skills/react-hook-form/SKILL.md

On react frontend framework work, also:

- ~/.agents/skills/react/SKILL.md

On UI/UX work — designing or reviewing anything that changes how the interface
looks, feels, or is interacted with (layout, color, typography, spacing, style
selection, accessibility, navigation patterns, animation, responsive behavior) —
also:

- ~/.agents/skills/ui-ux-pro-max/SKILL.md

Skip it for pure logic changes (backend, state management, data fetching) that
don't touch appearance or interaction.

On shadcn work, also:

- ~/.agents/skills/shadcn/SKILL.md
- ~/.agents/skills/ui-styling/SKILL.md

On shadcn work also:

- ~/.agents/skills/shadcn/SKILL.md

On tailwind work also:

- ~/.agents/skills/tailwind/SKILL.md

On tanstack-query work also:

- ~/.agents/skills/tanstack-query/SKILL.md

On zod work also:

- ~/.agents/skills/zod/SKILL.md

On frontend work also:

- ~/.agents/skills/frontend-ui-engineering/SKILL.md

On TypeScript work, also:

- ~/.agents/skills/typescript-clean-code/SKILL.md

On Python work, also:

- ~/.agents/skills/python-developer/SKILL.md

Skip these for non-coding questions.

Do not commit, push, or add dependencies unless asked. Prefer clarity over cleverness. Do not invent JWT claims.

## Customization boundary

Users customize through `backend/src/custom/` and `frontend/src/custom/` (see `documentations/customization/`). Never add, edit, or delete files there in core changes; upstream must ship nothing under them. Keep the extension hooks (`backend/src/extensions.py`, `frontend/src/extensions.ts`) and the stable modules listed there backward compatible; call out breaking changes. When a hook changes, update all three language files (en, es, fr) in `documentations/customization/`. Core Alembic migrations stay on the default branch; use `alembic upgrade heads`.

## Frontend routes

SPA in `frontend/src/router.ts`. Vite proxies `/api` (HTTP + WS) to `http://127.0.0.1:8000`.

Logged-in shell: `SessionGate` → `AppLayout` (header + sidebar + `<Outlet />`). `/login` is public; if the session is already ready, redirect home. English nav labels; show a sidebar link only when `can(permission)` passes. 404 is a child of AppLayout. Home is the index route.

FSD: `pages/<feature>/{ui,api,model,schema}`, `widgets/`, `shared/`, `layouts/`. Aliases: `@/` → `src/`, `@pages/` → `src/pages/`. Page API modules use `api` (`baseURL` `/api/v1`, `withCredentials`). UI copy is English.

## API routes

App routes hang off `/api/v1` (`backend/src/api/v1/`). One `APIRouter` per resource, `prefix` + `tags` matching the resource name.

Auth is cookies, not Bearer: `my_token`, `my_refresh`; CSRF cookie `csrf_access_token` as `X-CSRF-TOKEN` on POST/PUT/PATCH/DELETE. Never put the access token in a query string. WebSockets authenticate with `get_ws_payload` (cookie `my_token`, same-origin `Origin` required) and stay open through `api/ws.py` (`hold`), which re-checks the session every minute and closes with 4401 when the token expires or is revoked (the client refreshes and reconnects) or 4403 when access is lost.

Sessions: `POST /auth/logout` revokes both tokens (`revoked_tokens`, sha256 of the token); refresh tokens rotate on every use; a password change sets `users.sessions_valid_after`, signing the user out everywhere. `/auth/login` is throttled from the audit log (5 failures per email, 20 per IP, per 15 minutes). Passwords are at most 72 bytes (bcrypt).

HTTP guards: `Depends(get_current_user)` or `Depends(require_permission("resource.action"))`. `require_permission` is OR across its keys. No custom auth decorators.

REST shape:

- `GET ""` — paginated list: `page` (≥1), `per_page` (1–100, default 20), optional `q` (max 100). Body `{items, page, per_page, total, pages}`.
- `POST ""` — create, 201.
- `PATCH /{id}` or `PATCH /{key}` — update. Users and documents use numeric id; roles use `key`.
- `DELETE /{id}` or `DELETE /{key}` — 204, empty body.
- Forms that need roles or permissions call those list endpoints and only render the picker if `can("roles.list")` / `can("permissions.list")`.
- Document upload is multipart (`name`, `file`, `classification`), not JSON.

## Errors

Raise `AppError(code, message, status_code)` with an English message. Wire to `{code, message}`; the message is translated to `APP_LANGUAGE` on the way out (`i18n.py`), and text stored for later display (notifications, processing errors) is translated with `t()` when stored. Add es/fr translations to `i18n.py` for every new user-facing message. Codes: `unauthorized` 401, `forbidden` 403, `invalid` 400, `not_found` 404, `conflict` 409, `rate_limited` 429, `unavailable` 503, `misconfigured` 500. `code` is for branching; show `message` inline next to the action. No toasts.

## RBAC

Boolean permission keys `resource.action` from `/auth/me`. Frontend `can("users.list")`. No CASL. Permissions are a seeder catalog (no create/update/delete API). Seeder upserts catalog keys and deletes leftovers not assigned to any role; run `seed_permissions` before and after `seed_roles`. Role/permission **name and key are immutable after create** (`key_from_name` / `keyFromName`). Last admin user/role cannot be removed.

No escalation: an actor may only grant permissions they hold, and may only update or delete users and roles whose permissions they hold (`services/grant.py`). The Admin role always has every permission.

## Audit log

Every sign-in (and failure), sign-out, user/role create/update/delete, document upload/delete/view, and chat answer that used documents is recorded in `audit_logs`. Record in the router after the service call with `AuditService` from `Depends(get_audit_service)` (same session, commits with the action); action names are `AuditAction` values (`resource.verb`). Never record passwords, tokens, or chat question text. The log is append-only: no update or delete API. Viewing needs `audit.list` (`/audit` page). The user page (`/users/:id`, opened from the users list and the audit log) needs `users.view`: profile plus their history (`GET /users/{id}/activity`: their actions and failed sign-ins on their account, newest first by time). History uses cursor pages (`before` = last entry id, `next_cursor` null at the end) instead of `page`/`per_page`, for infinite scroll that stays stable while new entries arrive.

Document ACL (hierarchical): `standard` < `restricted` < `confidential` < `secret`. Higher permission includes lower. Same rules for list, delete, and RAG/chat retrieval. Postgres is source of truth; Qdrant payload is a duplicate for filters.

## Naming and layers

Python: one service per entity, singular (`UserService`). FastAPI routers stay thin; logic in services. Pydantic classes keep the `Schema` suffix; filenames are `user.py`, not `user_schema.py`. Inject with `Depends`, including `Form()` schemas for multipart.

## Deployment and secrets

`uv run setup` generates weak or missing secrets (JWT, DB, RabbitMQ, Qdrant, MinIO, `DATA_ENCRYPTION_KEY`) into `backend/.env`; compose re-applies DB and RabbitMQ passwords on restart. Local compose ports bind to `127.0.0.1`.

Production is `docker-compose.prod.yml` via `deploy/deploy.sh` (`build`, `models`, `up`, `admin EMAIL`, `logs`, `down`; see `documentations/deployment.md`). Every service sits on the `internal` network (`internal: true`, no internet) with no published ports; only `proxy` (Caddy: HTTPS, security headers, CSP, built frontend) is also on `edge` and publishes 80/443. Models are downloaded only by the `setup`-profile jobs `models`/`models-llm` on the `egress` network; containers run with `HF_HUB_OFFLINE=1`. Never add a runtime dependency on the internet (telemetry, update checks, model hubs). The backend image installs CPU PyTorch; it runs as a non-root user. `/docs` exists only with `API_DOCS=true`.

## Confidentiality

Document content is encrypted at rest with `DATA_ENCRYPTION_KEY` (`encryption.py`, AES-256-GCM): MinIO objects (`ObjectStorage`), `document_texts.text` and chat messages/titles (`EncryptedText` columns), Qdrant chunk text (`services/rag.py`). New stored content must use the same. Document names and vectors stay plain (name search, vector search). Never log document text, chat content or secrets. `maintenance.encrypt_existing` encrypts data stored before encryption.

## Tests

`cd backend && uv run pytest` (needs the local Postgres; tests create and drop their own database, other services are faked). Every security rule (sessions, RBAC, audit, ACL, encryption, privacy) has a test; add one with any change to them.

## Documents, RAG, chat

MinIO: the backend uses a least-privilege app user (`MINIO_ACCESS_KEY`: get/put/delete objects in `MINIO_BUCKET` only), never root. The bucket, policy and user are created by the `minio-init` compose service; the app must not create or list buckets. Object keys are `documents/<uuid>` with no filename. Uploads pass `services/documents/upload_check.py` (content matches extension, zip size limits) before conversion or storage.

Pipeline: upload (convert `.doc` → `.docx` if needed) → Postgres row + MinIO in the same request → Celery → parse (original saved to `document_texts`) → rules cleanup (`services/documents/text_cleanup.py`) → chunk (`CHUNK_SIZE`/`CHUNK_OVERLAP` from `.env`, read per job; set in `uv run setup`/`configure`, which warns when size + overlap exceeds the embedding model's input) → LLM cleanup (`TEXT_CLEANUP`, per-document time budget; skipped for CSV/JSON/XML/XLSX) → embed `EMBEDING_MODEL` → Qdrant. Only the embedded text is LLM-rewritten; the Qdrant payload keeps the rules-cleaned chunk and answers use the original, so a bad rewrite never reaches users. A rewrite that loses any number or changes length too much is discarded. Queue failures notify; HTTP upload errors stay on the form. Celery tasks import at module level (a broken import must stop the worker, not lose jobs), dispose the DB engine at the end of each `asyncio.run` (pooled connections are bound to one event loop), and the worker re-queues every unfinished document on start (`worker_ready`); processing is idempotent, so duplicates are harmless. One worker process (`worker_concurrency=1`) is assumed. Chat is a WebSocket on the chat router (`/ws`), same cookie auth as other sockets. Client and server exchange typed JSON (`ask` / `delta` / `answer` / `error`); `{code, message}` on errors. The answer streams as `delta` pieces, then `answer` carries the full text. Client may send `cancel` while a reply is running; the server stops generation and replies `cancelled`. Send the last 4–6 messages; embed/search only the latest user question. Chats are saved per user (`chat_conversations`/`chat_messages`, encrypted, private to the owner, deleted after `CHAT_RETENTION_DAYS`); the `answer` carries `conversation_id` and `sources` (documents used), which open through `GET /documents/{id}/file` (same clearance rule as chat, audited as `documents.view`). A document longer than its share of the LLM context is sent as excerpts around the search hits (`services/chat.py`, `build_excerpt`), joined exactly by the chunk `start` offsets in the Qdrant payload. Answer from the full text of matching documents: read it from `document_texts` (saved at processing time); only documents processed before that are parsed from MinIO once and then saved. Never re-parse per question. No LangChain. LLM via `LLM_HOST`, `LLM_MODEL` and a fixed `LLM_NUM_CTX` (never vary `num_ctx` per request: Ollama reloads the model); document context is cut to fit it. Chat is read-only: it must not create, change, or delete data, and it answers only about documents the user may see.
