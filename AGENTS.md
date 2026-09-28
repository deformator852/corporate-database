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

Users customize through `backend/src/custom/` and `frontend/src/custom/` (see `documentations/customization/`). Never add, edit, or delete files there in core changes; upstream must ship nothing under them. Keep the extension hooks (`backend/src/extensions.py`, `frontend/src/extensions.ts`) and the stable modules listed there backward compatible; call out breaking changes. When a hook changes, update all five language files in `documentations/customization/`. Core Alembic migrations stay on the default branch; use `alembic upgrade heads`.

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

Raise `AppError(code, message, status_code)`. Wire to `{code, message}`. Codes: `unauthorized` 401, `forbidden` 403, `invalid` 400, `not_found` 404, `conflict` 409, `rate_limited` 429, `unavailable` 503, `misconfigured` 500. `code` is for branching; show `message` inline next to the action. No toasts.

## RBAC

Boolean permission keys `resource.action` from `/auth/me`. Frontend `can("users.list")`. No CASL. Permissions are a seeder catalog (no create/update/delete API). Seeder upserts catalog keys and deletes leftovers not assigned to any role; run `seed_permissions` before and after `seed_roles`. Role/permission **name and key are immutable after create** (`key_from_name` / `keyFromName`). Last admin user/role cannot be removed.

No escalation: an actor may only grant permissions they hold, and may only update or delete users and roles whose permissions they hold (`services/grant.py`). The Admin role always has every permission.

## Audit log

Every sign-in (and failure), sign-out, user/role create/update/delete, document upload/delete, and chat answer that used documents is recorded in `audit_logs`. Record in the router after the service call with `AuditService` from `Depends(get_audit_service)` (same session, commits with the action); action names are `AuditAction` values (`resource.verb`). Never record passwords, tokens, or chat question text. The log is append-only: no update or delete API. Viewing needs `audit.list` (`/audit` page). The user page (`/users/:id`, opened from the users list and the audit log) needs `users.view`: profile plus their history (`GET /users/{id}/activity`: their actions and failed sign-ins on their account, newest first by time). History uses cursor pages (`before` = last entry id, `next_cursor` null at the end) instead of `page`/`per_page`, for infinite scroll that stays stable while new entries arrive.

Document ACL (hierarchical): `standard` < `restricted` < `confidential` < `secret`. Higher permission includes lower. Same rules for list, delete, and RAG/chat retrieval. Postgres is source of truth; Qdrant payload is a duplicate for filters.

## Naming and layers

Python: one service per entity, singular (`UserService`). FastAPI routers stay thin; logic in services. Pydantic classes keep the `Schema` suffix; filenames are `user.py`, not `user_schema.py`. Inject with `Depends`, including `Form()` schemas for multipart.

## Deployment and secrets

`uv run setup` generates weak or missing secrets (JWT, DB, RabbitMQ, Qdrant, MinIO) into `backend/.env`; compose re-applies DB and RabbitMQ passwords on restart. Every compose port binds to `127.0.0.1`. Production traffic goes through `deploy/Caddyfile` (`docker-compose.prod.yml`): HTTPS, security headers and CSP (no inline scripts in `index.html`), with uvicorn behind it on `--proxy-headers`. `/docs` and `/openapi.json` exist only with `API_DOCS=true`.

## Documents, RAG, chat

MinIO: the backend uses a least-privilege app user (`MINIO_ACCESS_KEY`: get/put/delete objects in `MINIO_BUCKET` only), never root. The bucket, policy and user are created by the `minio-init` compose service; the app must not create or list buckets. Object keys are `documents/<uuid>` with no filename. Uploads pass `services/upload_check.py` (content matches extension, zip size limits) before conversion or storage.

Pipeline: upload (convert `.doc` → `.docx` if needed) → Postgres row + MinIO in the same request → Celery → parse → chunk → embed `EMBEDING_MODEL` → Qdrant. Queue failures notify; HTTP upload errors stay on the form. Chat is a WebSocket on the chat router (`/ws`), same cookie auth as other sockets. Client and server exchange typed JSON (`ask` / `delta` / `answer` / `error`); `{code, message}` on errors. The answer streams as `delta` pieces, then `answer` carries the full text. Client may send `cancel` while a reply is running; the server stops generation and replies `cancelled`. Send the last 4–6 messages; embed/search only the latest user question. Answer from the full text of matching documents: read it from `document_texts` (saved at processing time); only documents processed before that are parsed from MinIO once and then saved. Never re-parse per question. No LangChain. LLM via `LLM_HOST`, `LLM_MODEL` and a fixed `LLM_NUM_CTX` (never vary `num_ctx` per request: Ollama reloads the model); document context is cut to fit it. Chat is read-only: it must not create, change, or delete data, and it answers only about documents the user may see.
