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

## Frontend routes

SPA in `frontend/src/router.ts`. Vite proxies `/api` (HTTP + WS) to `http://127.0.0.1:8000`.

Logged-in shell: `SessionGate` → `AppLayout` (header + sidebar + `<Outlet />`). `/login` is public; if the session is already ready, redirect home. English nav labels; show a sidebar link only when `can(permission)` passes. 404 is a child of AppLayout. Home is the index route.

FSD: `pages/<feature>/{ui,api,model,schema}`, `widgets/`, `shared/`, `layouts/`. Aliases: `@/` → `src/`, `@pages/` → `src/pages/`. Page API modules use `api` (`baseURL` `/api/v1`, `withCredentials`). UI copy is English.

## API routes

App routes hang off `/api/v1` (`backend/src/api/v1/`). One `APIRouter` per resource, `prefix` + `tags` matching the resource name.

Auth is cookies, not Bearer: `my_token`, `my_refresh`; CSRF cookie `csrf_access_token` as `X-CSRF-TOKEN` on POST/PUT/PATCH/DELETE. Never put the access token in a query string. WebSockets authenticate with `get_ws_payload` (cookie `my_token`).

HTTP guards: `Depends(get_current_user)` or `Depends(require_permission("resource.action"))`. `require_permission` is OR across its keys. No custom auth decorators.

REST shape:

- `GET ""` — paginated list: `page` (≥1), `per_page` (1–100, default 20), optional `q` (max 100). Body `{items, page, per_page, total, pages}`.
- `POST ""` — create, 201.
- `PATCH /{id}` or `PATCH /{key}` — update. Users and documents use numeric id; roles use `key`.
- `DELETE /{id}` or `DELETE /{key}` — 204, empty body.
- Forms that need roles or permissions call those list endpoints and only render the picker if `can("roles.list")` / `can("permissions.list")`.
- Document upload is multipart (`name`, `file`, `classification`), not JSON.

## Errors

Raise `AppError(code, message, status_code)`. Wire to `{code, message}`. Codes: `unauthorized` 401, `forbidden` 403, `invalid` 400, `not_found` 404, `conflict` 409, `unavailable` 503, `misconfigured` 500. `code` is for branching; show `message` inline next to the action. No toasts.

## RBAC

Boolean permission keys `resource.action` from `/auth/me`. Frontend `can("users.list")`. No CASL. Permissions are a seeder catalog (no create/update/delete API). Seeder upserts catalog keys and deletes leftovers not assigned to any role; run `seed_permissions` before and after `seed_roles`. Role/permission **name and key are immutable after create** (`key_from_name` / `keyFromName`). Last admin user/role cannot be removed.

Document ACL (hierarchical): `standard` < `restricted` < `confidential` < `secret`. Higher permission includes lower. Same rules for list, delete, and RAG/chat retrieval. Postgres is source of truth; Qdrant payload is a duplicate for filters.

## Naming and layers

Python: one service per entity, singular (`UserService`). FastAPI routers stay thin; logic in services. Pydantic classes keep the `Schema` suffix; filenames are `user.py`, not `user_schema.py`. Inject with `Depends`, including `Form()` schemas for multipart.

## Documents, RAG, chat

Pipeline: upload (convert `.doc` → `.docx` if needed) → Postgres row + MinIO in the same request → Celery → parse → chunk → embed `EMBEDING_MODEL` → Qdrant. Queue failures notify; HTTP upload errors stay on the form. Chat is a WebSocket on the chat router (`/ws`), same cookie auth as other sockets. Client and server exchange typed JSON (`ask` / `answer` / `error`); `{code, message}` on errors. Client may send `cancel` while a reply is running; the server stops generation and replies `cancelled`. Send the last 4–6 messages; embed/search only the latest user question. Load full matching files from MinIO when answering. No LangChain. LLM via `LLM_HOST` and `LLM_MODEL` only. Chat is read-only: it must not create, change, or delete data, and it answers only about documents the user may see.
