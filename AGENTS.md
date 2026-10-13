# Agent

On coding tasks, read and follow:

- .skills/karpathy/SKILL.md — HOW to work: clarify ambiguity and state
  assumptions before coding, make surgical changes only, match existing style,
  define success criteria and verify (tests/run) before finishing.
- .skills/ponytail/SKILL.md — WHAT to build: the smallest solution that
  works. Check in order: is it needed at all → already in repo → stdlib →
  platform feature → dependency → custom code. No speculative abstractions.

Both apply to every coding task. Order: karpathy first (understand, scope),
then ponytail (minimize the solution), then karpathy again (verify).

On conflict:

- Existing codebase conventions and readability beat ponytail's line-count golf.
- Never minimize validation, error handling, security, or tests.
- Mature/team repo → ponytail lite; prototypes/scripts → ponytail full.

On writing any sort of documentation or text, also:

- .skills/technical-writer/SKILL.md

On testing tasks, also:

- .skills/qa/SKILL.md

On react hook form work, also:

- .skills/react-hook-form/SKILL.md

On react frontend framework work, also:

- .skills/react/SKILL.md

On UI/UX work — designing or reviewing anything that changes how the interface
looks, feels, or is interacted with (layout, color, typography, spacing, style
selection, accessibility, navigation patterns, animation, responsive behavior) —
also:

- .skills/ui-ux-pro-max/SKILL.md

Skip it for pure logic changes (backend, state management, data fetching) that
don't touch appearance or interaction.

On shadcn work, also:

- .skills/shadcn/SKILL.md
- .skills/ui-styling/SKILL.md

On shadcn work also:

- .skills/shadcn/SKILL.md

On tailwind work also:

- .skills/tailwind/SKILL.md

On tanstack-query work also:

- .skills/tanstack-query/SKILL.md

On zod work also:

- .skills/zod/SKILL.md

On frontend work also:

- .skills/frontend-ui-engineering/SKILL.md

On TypeScript work, also:

- .skills/typescript-clean-code/SKILL.md

On Python work, also:

- .skills/python-developer/SKILL.md

Skip these for non-coding questions.

Do not commit, push, or add dependencies unless asked. Prefer clarity over cleverness. Do not invent JWT claims.

## Customization boundary

Users customize through `backend/src/custom/` and `frontend/src/custom/` (see `documentations/customization/`). Never add, edit, or delete files there in core changes; upstream must ship nothing under them. Keep the extension hooks (`backend/src/extensions.py`, `frontend/src/extensions.ts`) and the stable modules listed there backward compatible; call out breaking changes. When a hook changes, update all three language files (en, es, fr) in `documentations/customization/`. Core Alembic migrations stay on the default branch; use `alembic upgrade heads`.

Core code never imports from `custom/`, and runs unchanged without it. Each custom package may declare `CORE_API` (backend) or `coreApi` (frontend); a package written for another version is skipped with an error. Bump `CORE_API` in both `extensions.py` and `extensions.ts` when an extension point changes incompatibly.

## Frontend routes

SPA in `frontend/src/router.ts`. Vite proxies `/api` (HTTP + WS) to `http://127.0.0.1:8000`.

Logged-in shell: `SessionGate` → `AppLayout` (header + sidebar + `<Outlet />`). `/login` is public; if the session is already ready, redirect home. English nav labels; show a sidebar link only when `can(permission)` passes. 404 is a child of AppLayout. Home is the index route.

FSD: `pages/<feature>/{ui,api,model,schema}`, `widgets/`, `entities/<entity>/{api,model}`, `shared/`, `layouts/`. A layer imports only from layers below it (pages → widgets → entities → shared), and a page never from another page: what two pages share (documents' statuses, role and permission lists, the audit model) lives in `entities/`. List pages use `shared/lib/hooks/useRequest` (load, stale-answer drop, reload, in-place update) and `usePageParam`, `shared/ui/ListPagination` and `StatusCard`; searchable checkbox lists use `shared/ui/SearchablePicker`. Every delete action is `shared/ui/DeleteButton` (red, trash icon, "Delete"; `sm` in rows, cards and action groups, default size in a page header) behind a `ConfirmDialog`; never an icon-only delete. List pages use `shared/ui/PageHeader` and `DataTable`. Effects read the latest props through `useEffectEvent`, not refs or missing dependencies; forms read fields with `useWatch`, not `watch`. Frontend checks: `npx tsc -b`, `npx oxlint src`, `npx vitest run`. Aliases: `@/` → `src/`, `@pages/` → `src/pages/`. Page API modules use `api` (`baseURL` `/api/v1`, `withCredentials`). UI copy is English.

## API routes

App routes hang off `/api/v1` (`backend/src/api/v1/`). One `APIRouter` per resource, `prefix` + `tags` matching the resource name.

Auth is cookies, not Bearer: `my_token`, `my_refresh`; CSRF cookie `csrf_access_token` as `X-CSRF-TOKEN` on POST/PUT/PATCH/DELETE. Never put the access token in a query string. WebSockets authenticate with `get_ws_payload` (cookie `my_token`, same-origin `Origin` required) and stay open through `api/ws.py` (`hold`), which re-checks the session every minute and closes with 4401 when the token expires or is revoked (the client refreshes and reconnects) or 4403 when access is lost.

SSO (OpenID Connect, `services/sso.py`, off while `OIDC_ISSUER` is empty): `GET /auth/sso/start` redirects to the provider with state, nonce and a PKCE verifier kept in a signed, HttpOnly cookie scoped to `/api/v1/auth/sso`; `GET /auth/sso/callback` exchanges the code (client secret + verifier), checks the ID token (provider's keys, asymmetric algorithms only, `iss`, `aud`, `exp`, `nonce`) and redirects to `/` signed in, or to `/login?sso_error=CODE` (never the provider's text). Also `azp` must be ours when present or when there are several audiences; the client secret goes as `client_secret_basic` unless the provider only takes `client_secret_post`. Accounts match `users.oidc_subject` ("ISSUER SUB"), never email; only a trusted email (an `email` claim not marked `email_verified: false`; never `preferred_username`) may link or rename an existing account; the first sign-in creates the account (no password) or, with `OIDC_LINK_BY_EMAIL`, takes over the one with that email. `OIDC_ROLE_MAP` roles follow the groups claim at each sign-in; other roles stay. With SSO on, `POST /auth/login` accepts passwords of Admin-role holders only (others get `sso_required`, after the password check); the sign-in page puts that form behind a link (`services/password.uses_password`). `GET /auth/methods` (public) tells the sign-in page what to show. Production reaches the provider only through `sso-tunnel` (`OIDC_CONNECT`, like Vault's). Set up in `uv run setup`/`configure` (step Sign-in). Sessions end 12 hours after the sign-in however active (`security.SESSION_MAX_AGE`; tokens carry `signed_in_at`, which a refresh keeps); the backend refuses to start with a `JWT_SECRET_KEY` under 32 characters; the frontend refreshes one tab at a time (Web Locks), as each refresh token works once. bcrypt runs in a thread (`asyncio.to_thread`), never on the event loop. Sessions: `POST /auth/logout` revokes both tokens (`revoked_tokens`, sha256 of the token); refresh tokens rotate on every use; a password change sets `users.sessions_valid_after`, signing the user out everywhere. `/auth/login` is throttled from the audit log (5 failures per email, 200 per IP, per 15 minutes); an unknown email is checked against a stand-in hash, so timing does not reveal accounts. `POST /auth/password` (current + new password, page `/account`) changes the user's own password: wrong current passwords count as failed sign-ins (400, not 401), and success ends every session of the user, this one too. Passwords are at most 72 bytes (bcrypt).

HTTP guards: `Depends(get_current_user)` or `Depends(require_permission("resource.action"))`. `require_permission` is OR across its keys. No custom auth decorators.

REST shape:

- `GET ""` — paginated list: `page` (≥1), `per_page` (1–100, default 20), optional `q` (max 100). Body `{items, page, per_page, total, pages}`.
- `POST ""` — create, 201.
- `PATCH /{id}` or `PATCH /{key}` — update. Users and documents use numeric id; roles use `key`.
- `DELETE /{id}` or `DELETE /{key}` — 204, empty body.
- Forms that need roles or permissions call those list endpoints and only render the picker if `can("roles.list")` / `can("permissions.list")`.
- Document upload is multipart (`name`, `file`, `classification`), not JSON.

## Errors

Raise `AppError(code, message, status_code)` with an English message. Wire to `{code, message}`; the message is translated on the way out (`i18n.py`) to the current language, and text stored for later display (notifications, processing errors) is translated with `t()` when stored, in its owner's language. Languages: `APP_LANGUAGE` is the default, `APP_LANGUAGES` the ones users switch between in the header (`widgets/language-switcher`, hidden with one; both baked into the frontend build like `APP_LANGUAGE`). The choice is saved in `users.language` (`PUT /auth/language`). The current language (`i18n.use_language`, a context variable) comes from the request's `Accept-Language` (the frontend sends its locale), replaced by the user's choice in `get_current_user`; the chat socket reads the user's choice per message, and worker jobs take the document owner's (`DocumentProcessor._require`). The assistant answers in the current language. Several languages need a multilingual embedding model; `uv run setup`/`configure` ask for them and offer only such models. Add es/fr translations to `i18n.py` for every new user-facing message. Codes: `unauthorized` 401, `forbidden` 403, `invalid` 400, `not_found` 404, `conflict` 409, `rate_limited` 429, `unavailable` 503, `misconfigured` 500. `code` is for branching; show `message` inline next to the action. No toasts.

## RBAC

Boolean permission keys `resource.action` from `/auth/me`. Frontend `can("users.list")`. No CASL. Permissions are a seeder catalog (no create/update/delete API). Seeder upserts catalog keys and deletes leftovers not assigned to any role; run `seed_permissions` before and after `seed_roles`. Role/permission **name and key are immutable after create** (`key_from_name` / `keyFromName`). Last active admin user/role cannot be removed or disabled.

Offboarding is `users.disable` (`POST /users/{id}/disable|enable`), not deletion: `users.disabled_at` blocks sign-in (403 only after the right password, so it does not reveal accounts) and `user_session_valid` rejects every session of a disabled user at once; the account, its documents and audit history stay. Nobody can disable themselves.

No escalation: an actor may only grant permissions they hold, and may only update or delete users and roles whose permissions they hold (`services/grant.py`). The Admin role always has every permission.

## Audit log

Every sign-in (and failure), sign-out, user/role create/update/delete, user disable/enable, document upload/update/retry/delete/view, chat answer that used documents, reading another user's chat (`chat.view`) and clearing chat history (`chat.purge`) is recorded in `audit_logs`. Record in the router after the service call with `AuditService` from `Depends(get_audit_service)` (same session, commits with the action); action names are `AuditAction` values (`resource.verb`). Never record passwords, tokens, or chat question text. The log is append-only: no update or delete API. Viewing needs `audit.list` (`/audit` page). The user page (`/users/:id`, opened from the users list and the audit log) needs `users.view`: profile plus their history (`GET /users/{id}/activity`: their actions and failed sign-ins on their account, newest first by time). History uses cursor pages (`before` = last entry id, `next_cursor` null at the end) instead of `page`/`per_page`, for infinite scroll that stays stable while new entries arrive.

Error log (`services/error_log.py`, `error_logs`, page `/errors`, permission `system.errors`): `error_log.install(source)` (backend lifespan, worker `after_setup_logger`) adds a WARNING handler to the root and `uvicorn` loggers; records go to a queue written in batches by a per-process thread with its own NullPool engine (recreated after a fork: Celery's pool). Message and traceback are encrypted. Unhandled API errors go through the app's `Exception` handler: logged once with method and path (never the query string), marked `LOGGED` so uvicorn's copy is skipped, answered 500 `{code: "internal"}`. Never log document text, chat content or secrets: the log is shown to admins. At most 30 entries per logger per minute are kept (a damaged PDF can warn per object). Entries older than `ERROR_LOG_RETENTION_DAYS` (default 30, 0 = forever) are deleted by the purge loop. The engine uses `hide_parameters=True`, so SQL errors do not carry row values. Each entry has a `category`: `unhandled` (a bug nothing caught: the app's HTTP handler, `main.SocketErrors` for sockets, uvicorn, Celery task failures), `app` (a logger of Corpus's own modules) or `library` (any other logger; only its errors are kept, its warnings reach the console alone); log with `extra={"category": ...}` to say it explicitly. Frontend errors are not stored.

Document ACL (hierarchical): `standard` < `restricted` < `confidential` < `secret`. Higher permission includes lower. Same rules for list, delete, and RAG/chat retrieval. Postgres is source of truth; Qdrant payload is a duplicate for filters.

## Naming and layers

Python: one service per entity, singular (`UserService`). FastAPI routers stay thin; logic in services. Pydantic classes keep the `Schema` suffix; filenames are `user.py`, not `user_schema.py`. Inject with `Depends`, including `Form()` schemas for multipart. Inject the database session as `Depends(get_db, scope="function")`: the default scope commits after the response is sent, so clients would get 200 for unsaved changes and read stale data. Socket handlers are protocol only too: the chat question/answer use case is `services/chat/turn.py`. Data passed between services is typed (`@dataclass(frozen=True, slots=True)`, e.g. `SearchHit`, `ContextDocument`), not `dict[str, object]`. Backend checks: `uv run ruff check`, `uv run ruff format --check` (line length 120, rules E F W I B C4 UP) and `uv run ty check src` pass before a change is done.

## Deployment and secrets

Settings come from the process environment only (`settings.py`: development loads `backend/.env` at start, production gets compose `environment:`), read once per start: no live reload of `.env`; after `setup`/`configure`, restart backend and worker. `uv run setup` generates weak or missing secrets (JWT, DB, RabbitMQ, Qdrant, MinIO, `DATA_ENCRYPTION_KEY`) into `backend/.env`; compose re-applies DB and RabbitMQ passwords on restart. Local compose ports bind to `127.0.0.1`.

Production is `docker-compose.prod.yml` via `deploy/deploy.sh` (`build`, `models`, `up`, `admin EMAIL`, `backup [DIR]`, `restore DIR`, `rotate-key`, `logs`, `down`; see `documentations/deployment.md`). No service uses `env_file`: each lists only the variables it needs under `environment:` (filled from `backend/.env` by `--env-file`), in groups (`x-db-env` → migrate, `x-worker-env` → worker, + JWT secret → backend), and the internet-facing `models` job gets no secrets. Keep it that way when adding a variable. Generated secrets never start with `-` (`setup/env.py: random_secret`), and shell commands pass them after `--`. Every service sits on the `internal` network (`internal: true`, no internet) with no published ports; only `proxy` (Caddy: HTTPS, security headers, CSP, built frontend) is also on `edge` and publishes 80/443. Models are downloaded only by the `setup`-profile jobs `models`/`models-llm` on the `egress` network; `deploy.sh up` checks offline (`download_models --check`, the Ollama manifest) and runs the missing ones in parallel before starting; containers run with `HF_HUB_OFFLINE=1`. With `KEY_STORE=vault`, deploy.sh adds the `vault` profile: `vault-tunnel` (socat, on `internal` and `egress`) forwards to `VAULT_ADDR`'s host:port only, and backend/worker dial it via `VAULT_CONNECT` with TLS still checked against Vault's name (`sni_hostname`). Never add a runtime dependency on the internet (telemetry, update checks, model hubs). The backend image installs CPU PyTorch; it runs as a non-root user. `/docs` exists only with `API_DOCS=true`.

## Confidentiality

The key comes from `key_store.py`: `.env` (`KEY_STORE=env`, default) or HashiCorp Vault (`KEY_STORE=vault`: AppRole `VAULT_ROLE_ID`/`VAULT_SECRET_ID`, KV v2 `VAULT_KV_MOUNT`/`VAULT_KV_PATH`, fields `DATA_ENCRYPTION_KEY`/`_PREVIOUS`, read once per process, memory only). `uv run setup`/`configure` (`setup/steps/key_store.py`) move the key between them with a one-time admin token, never overwriting another key in Vault; `setup key rotate|finish` write rotations to Vault; the secrets step never generates a key in `.env` while it is in Vault. No HSM integration: an HSM belongs behind Vault. Document content is encrypted at rest with `DATA_ENCRYPTION_KEY` (`encryption.py`, AES-256-GCM): MinIO objects (`ObjectStorage`), `document_texts.text` and chat messages/titles (`EncryptedText` columns), Qdrant chunk text (`services/search/rag.py`). New stored content must use the same. Document names and vectors stay plain (name search, vector search). Never log document text, chat content or secrets.

Values carry the id of the key that sealed them (`enc:v2:`, `CRPSENC2`). Decryption is strict: a value without the marker raises instead of being read as plain text (it could be planted by anyone with write access to a store). `system_state.encryption_key_fingerprint` records the data's key; backend (lifespan) and worker (`worker_init`) refuse to start with another key (`services/encryption_key.py`). Rotation: `uv run setup key rotate` (old key → `DATA_ENCRYPTION_KEY_PREVIOUS`, new key, backup confirmation), then `deploy/deploy.sh rotate-key` (`maintenance.rotate_key`: re-encrypts MinIO, Postgres, Qdrant, records the fingerprint; resumable). A new encrypted store must be added to `maintenance/rotate_key.py`. `uv run setup key [--show]` prints the fingerprint (and the key).

Backups (`deploy.sh backup`): the app stops, then `pg_dump` and gzip tars of the `minio_data`/`qdrant_data` volumes are streamed through `maintenance.backup_crypt` (`encrypt_stream`: AES-GCM chunks with a per-file HKDF key, key id in the header, truncation detected), so nothing plain touches the disk. `restore` decrypts every part before deleting anything. A new data volume or store must be added to `VOLUMES` in `deploy.sh`.

## Tests

Every feature has a test; add or change one with any behaviour change. Test through the public surface (HTTP API, WebSocket, CLI, rendered UI), not internals. CI (`.github/workflows/tests.yml`) runs both suites on every PR with coverage gates (backend 85%, frontend 75% of lines).

Backend: `cd backend && uv run pytest` (needs only the local Postgres; each run creates and drops its own database). The `infra` fixture (`tests/fakes.py`, used by `client`) replaces services at the network boundary only: MinIO (dict), Qdrant (its in-memory mode, real filters and search), embeddings (word-hash vectors), Ollama (scripted), RabbitMQ (in-process fanout that reaches TestClient sockets), Celery (records jobs). `process(id)` runs the worker's job; `upload(...)` posts a file. Every security rule (sessions, RBAC, audit, ACL, encryption, privacy, limits) has a test.

Frontend: `cd frontend && npm test` (Vitest, jsdom, Testing Library). `renderApp(path, user, script)` (`src/test/app.tsx`) renders the real routes against a scripted server (`src/test/api.ts` swaps the axios transport, so API functions, CSRF and token refresh run for real; an unscripted request fails). `FakeWebSocket.at(path)` plays the server side of sockets; `scrollToEnd()` fires infinite-scroll observers. Query by role and label as a user would, never by CSS classes.

## Documents, RAG, chat

MinIO: the backend uses a least-privilege app user (`MINIO_ACCESS_KEY`: get/put/delete objects in `MINIO_BUCKET` only), never root. The bucket, policy and user are created by the `minio-init` compose service; the app must not create or list buckets. Object keys are `documents/<uuid>` with no filename. Uploads pass `services/documents/upload_check.py` (content matches extension, zip size limits) before conversion or storage.

Pipeline: upload (convert `.doc` → `.docx` if needed) → Postgres row + MinIO in the same request → Celery → parse (original saved to `document_texts`) → chunk the original text at its sections first (Markdown headings; the parser turns Word and ODT headings into them; small neighbouring sections stay together up to the chunk size; `processor._split_text`), then by size (`CHUNK_SIZE`/`CHUNK_OVERLAP`; set in `uv run setup`/`configure`, which warns when size + overlap exceeds the embedding model's input) → rules cleanup of each chunk for embedding only (`TEXT_CLEANUP`=rules|off, `services/documents/text_cleanup.py`): page furniture is found over the whole document — for PDFs (pages joined by `parser.PAGE_BREAK`) only lines at the page edges, digits masked; for other files short lines repeated 3+ times and page-number lines — and lines of 40+ characters that 5+ documents share are left out too (`services/documents/boilerplate.py`, keyed digests in `document_lines`); CSV/JSON/XML/XLSX get character fixes only; CSV/XLSX chunks after the first are embedded with the header row in front (`services/documents/embedding_text.py`). PDF pages with ruled tables are read by pdfplumber (a row per line, cells tab-separated); other pages by pypdf, which keeps multi-column text in column order → embed `EMBEDDING_MODEL` → Qdrant, with a sparse keyword vector per chunk next to the dense one (`services/search/keywords.py`; word ids are keyed digests; Qdrant applies IDF). Search runs both: vector hits pass `min_score`; keyword hits pass only when they hold every name and code of the question word for word (`exact`: words with a digit or capitalized past the first word, neighbours joined into phrases) and rank first. A collection without the keyword index is refused once it holds points. The Qdrant payload and `document_texts` keep the original text: cleanup rules drop lines (repeated values, numbers that look like page numbers) and must never change what search results, excerpts and answers show. There is no LLM cleanup: `evals/text_cleanup.py` measured it with no steady gain over the rules at 10–24 s per chunk. Do not prefix chunks with the document name or section path: `evals/chunk_context.py` measured it hurting search more often than helping. Queue failures notify; HTTP upload errors stay on the form. The form takes up to 50 files (`MAX_UPLOAD_FILES`) and sends them one request each; the server refuses uploads with `rate_limited` (429) while a user has `MAX_WAITING_DOCUMENTS` (100) documents queued or processing, since the single worker serves everyone in turn. Ready notices are grouped: a completed document gets `ready_unannounced`, and `NotificationService.announce_ready` sends one notice (`document.completed`, or `documents.completed` for several) once none of the owner's documents waits; processing failures still notify one by one. Celery tasks import at module level (a broken import must stop the worker, not lose jobs), dispose the DB engine at the end of each `asyncio.run` (pooled connections are bound to one event loop), and the worker re-queues every unfinished document on start (`worker_ready`); processing is idempotent, so duplicates are harmless. One worker process (`worker_concurrency=1`) is assumed. Chat is a WebSocket on the chat router (`/ws`), same cookie auth as other sockets. Client and server exchange typed JSON (`ask` / `delta` / `answer` / `error`); `{code, message}` on errors. The answer streams as `delta` pieces, then `answer` carries the full text. Client may send `cancel` while a reply is running; the server stops generation and replies `cancelled`. `ask` may carry `document_ids` (up to 20): the search and the answer use only those documents, and their hits skip `min_score` (the user chose them). `replace_message_id` regenerates: it must be the chat's last message, an answer; the question is not saved again and the new answer replaces the old one once saved. Documents are edited (`PATCH /documents/{id}`, `documents.update`: name, classification) only when processing is over; the change goes to Postgres, the Qdrant payload of every chunk and the source names of saved chat answers. `POST /documents/{id}/retry` (`documents.create`) queues a failed document again; failed documents list first. If the client leaves (tab closed, network lost) the server finishes the answer and saves it to the chat history; Stop and an ended session still stop it. The client sends up to 40 messages; the LLM gets the newest that fit a quarter of `LLM_NUM_CTX` (the oldest kept may be cut), a quarter is the answer, documents get the rest (`services/chat/generator.py`). Search with the latest user question and with it joined to the previous user question (follow-ups like "what about sales?" match nothing alone), best score per chunk. Chats are saved per user (`chat_conversations`/`chat_messages`, encrypted, deleted after `CHAT_RETENTION_DAYS`); owners cannot delete them, and search them with `GET /chat/conversations?q=` (titles and messages are encrypted, so the user's chats are decrypted and searched in Python). Each saved source carries `chunk`: the chunk of that document closest to the answer (`ChatService.cite`, by the answer's vector), shown through `GET /documents/{id}/chunks/{n}` (same clearance as the file, audited as `documents.view`; `page` for PDFs, counted by `parser.PAGE_BREAK`). Only `/chat/review/*` reaches other users' chats (`services/chat/review.py`, page `/chat-history`): `chat.history` reads them, `chat.purge` deletes one chat (`DELETE /chat/review/conversations/{id}`, audited as `chat.delete`) or those last active in a period (all, presets, or dates), whole, ratings included; both reach only users holding no permission the actor lacks, like managing users; the `answer` carries `conversation_id` and `sources` (documents used), which open through `GET /documents/{id}/file` (same clearance rule as chat, audited as `documents.view`). A document longer than its share of the LLM context is sent as excerpts around the search hits (`services/chat/excerpts.py`), joined exactly by the chunk `start` offsets in the Qdrant payload. Answer from the full text of matching documents, read from `document_texts` (saved at processing time); never parse files per question. No LangChain. LLM via `LLM_HOST`, `LLM_MODEL` and a fixed `LLM_NUM_CTX` (never vary `num_ctx` per request: Ollama reloads the model); document context is cut to fit it. Chat is read-only: it must not create, change, or delete data, and it answers only about documents the user may see. The index's model is recorded in `system_state` (`services/search/index_model.py`); backend and worker refuse to start when `EMBEDDING_MODEL` names another one (models of one size are not told apart by Qdrant). Switching is `uv run switch-embedding-model MODEL` (`src/switch_embedding_model`, like setup/configure, never in deploy.sh): production (prod stack running) downloads with the `models` job, stops the backend/worker containers, runs `maintenance/switch_embedding.py` in the backend image, writes `.env`, starts them; development stops this checkout's uvicorn/celery processes (found by argv and cwd), checking the model loads first. The rebuild drops the collection, queues every completed document with `reindexing` set (no ready notice when it completes again) and records the model; the worker re-processes them from MinIO on start (`worker_ready`). Run with the current model to rebuild the index. Re-chunking after a CHUNK_SIZE/CHUNK_OVERLAP change is optional: each document records the settings it was cut with (`documents.chunk_size/chunk_overlap`); `POST /system/rechunk` (`system.rechunk`, audited, page `/system`) marks the completed ones cut otherwise (`services/documents/rechunk.py`), and the worker task `documents.rechunk_next` claims one, re-cuts it from `document_texts` (`DocumentProcessor.rechunk`: status stays completed, new chunks overwrite, extra old ones are deleted), then queues itself again, so uploads wait for one document only; `worker_ready` resumes it. Every signed-in user sees the progress in a banner fed by the socket `/system/reindex/ws` (`services/search/reindex_hub.py`): the percentage on connect, then again after each document event the worker publishes; a percentage, never counts (they would reveal documents above the user's clearance). Relevance: search hits below the embedding model's `min_score` (settings.py, calibrated per model with `evals/search_relevance.py`, which adds `dataset_long.LANG.json` where it exists; English models take the lower value of chunks 400 and 800) are not used unless `exact`; a new model gets its value from that script. When no document passes, the server answers `NO_DOCUMENTS_ANSWER` ("I don't know…") without calling the LLM: given only the chat history, it invents sourced-looking answers. Sources shown are the documents the model names in its closing `SOURCES:` line (cut from the text and the stream, `services/chat/answer_sources.py`) that the answer also draws on (shared fact words); `evals/chat_sources.py` measures this end to end. The audit log records every document the model read, not only the sources shown. Chat limits (`services/chat/limit.py`, `chat_requests`): one answer at a time per user across tabs and processes (partial unique index on open rows; freed in `_answer`'s `finally`, rows older than 15 min count as crashed), and `CHAT_QUESTIONS_PER_10_MIN` questions per user (default 20, 0 = off, set in setup/configure). Refusals are socket errors `busy` / `rate_limited`; the client puts the question back in the input. Ollama answers `LLM_PARALLEL` questions at once (`OLLAMA_NUM_PARALLEL`, flash attention, q8_0 KV cache); every slot reserves `LLM_NUM_CTX` of context memory, which the configure step estimates.
