# Customization

Other languages: [Español](es.md) · [Українська](uk.md) · [Türkçe](tr.md) · [Français](fr.md)

## How it works

All your changes live in two folders. Upstream updates never ship files there,
so pulling a new version merges without conflicts:

| Folder | What goes there |
|---|---|
| `backend/src/custom/<name>/` | Python packages: API endpoints, models, permissions, background tasks |
| `backend/src/custom/migrations/` | Your Alembic migrations |
| `frontend/src/custom/<name>/index.ts(x)` | Pages, sidebar links, translations, themes |

`<name>` is any name you choose (`crm`, `hr`, …). You can have several. They load
in alphabetical order, and folders starting with `_` are skipped. Nothing needs
to be registered in core files: both folders are discovered automatically.

You can still edit core files, but each such edit may conflict on the next
update. Use an extension first, and edit core only when there is no hook for it
(see [Limitations](#limitations)).

## Getting updates

```sh
git remote add upstream <upstream repo url>   # once
git pull upstream main
cd backend && uv run alembic upgrade heads     # "heads": core + custom branches
cd src && uv run python -m seeders.run         # new core + custom permissions
```

Restart the backend, the Celery worker and the frontend dev server afterwards.

## Backend

A package `backend/src/custom/<name>/__init__.py` may define any of these:

| Name | What it does |
|---|---|
| `router` | `APIRouter` mounted under `/api/v1` **before** core routers |
| `PERMISSIONS` | `((key, name, description), ...)` seeded together with core permissions |
| `setup(app)` | Called once with the FastAPI app at startup |
| models | Any SQLAlchemy model imported by the package is visible to Alembic |
| `tasks.py` | Loaded by the Celery worker if present |

### New API endpoints

```python
# backend/src/custom/crm/api.py
from fastapi import APIRouter, Depends

from api.deps import get_current_user, require_permission
from models import User

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("/hello")
async def hello(user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"hello": user.first_name}


@router.get("/report")
async def report(_user: User = Depends(require_permission("crm.report"))) -> dict:
    return {"ok": True}
```

```python
# backend/src/custom/crm/__init__.py
from .api import router
```

The endpoint is served at `/api/v1/crm/hello`. Follow the project rules for
auth and errors: `Depends(get_current_user)` / `require_permission(...)`, and
`raise AppError(code, message, status_code)` from `exceptions`.

### Replacing a core endpoint

Custom routers are mounted first, so a route with the same method and path wins.
This replaces `GET /api/v1/users`:

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Keep the response shape the core frontend expects, or replace the page too.

### Permissions

```python
# backend/src/custom/crm/__init__.py
PERMISSIONS = (
    ("crm.report", "CRM report", "View the CRM report"),
)
```

After `seeders.run` they appear in the permissions list and can be assigned to
roles. The admin role receives them automatically. Use `resource.action` keys
that do not collide with core resources.

### `setup(app)`: overrides, middleware, handlers

```python
# backend/src/custom/crm/__init__.py
from fastapi import FastAPI


def setup(app: FastAPI) -> None:
    app.dependency_overrides[some_core_dependency] = my_dependency

    @app.middleware("http")
    async def add_header(request, call_next):
        response = await call_next(request)
        response.headers["X-Company"] = "ACME"
        return response
```

`app.dependency_overrides` replaces any function that core injects with
`Depends(...)`, everywhere at once.

### Models and extra user data

Do not add columns to core tables such as `users`. Put your data in your own
table with a one-to-one key. Core can then change its tables freely.

```python
# backend/src/custom/crm/models.py
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models import User


class UserProfile(Base):
    __tablename__ = "custom_user_profiles"  # prefix avoids clashes with future core tables

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    phone: Mapped[str | None] = mapped_column(String(32))
    user: Mapped[User] = relationship(backref="profile")  # user.profile works too
```

```python
# backend/src/custom/crm/__init__.py
from . import models  # noqa: F401  (registers the table)
from .api import router
```

Independent tables (not linked to users) work the same way.

### Migrations

Custom migrations are on their own Alembic branch, `custom`, so core migrations
never collide with them.

```sh
cd backend
uv run alembic upgrade heads          # database up to date first
mkdir -p src/custom/migrations

# first custom migration only: start the "custom" branch after the core head
uv run alembic revision --autogenerate -m "crm profiles" \
  --head base --branch-label custom --version-path src/custom/migrations \
  --depends-on $(uv run alembic heads | awk '{print $1; exit}')

# every next one
uv run alembic revision --autogenerate -m "..." --head custom@head

uv run alembic upgrade heads
```

Always use `upgrade heads` (plural). Check each generated file before applying it.

### Background tasks (Celery)

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Call it with `sync.delay()` from your endpoint. Use a `name` prefixed with your
extension to avoid collisions.

## Frontend

A file `frontend/src/custom/<name>/index.tsx` default-exports an `Extension`
(type in `frontend/src/extensions.ts`):

| Field | What it does |
|---|---|
| `routes` | Pages inside the logged-in layout (header + sidebar) |
| `nav` | Sidebar links, after the core ones |
| `messages` | Translations per language |
| `themes` | Extra themes in the theme picker |
| `defaultTheme` | Theme for users who have not picked one |

### New page with a sidebar link

```tsx
// frontend/src/custom/crm/Report.tsx
import {useI18n} from "@/shared/i18n/I18nProvider";

export function Report() {
    const {t} = useI18n();
    return <h1>{t("custom.crm.title")}</h1>;
}
```

```tsx
// frontend/src/custom/crm/index.tsx
import type {Extension} from "@/extensions";
import {Report} from "./Report";

export default {
    routes: [{path: "crm", Component: Report}],
    nav: [{to: "/crm", labelKey: "custom.crm.title", end: true, can: "crm.report"}],
    messages: {
        en: {"custom.crm.title": "CRM report"},
        uk: {"custom.crm.title": "Звіт CRM"},
    },
} satisfies Extension;
```

`can` hides the link from users without that permission. Inside a page, use
`can("crm.report")` from `@/shared/lib/api/me`. Call your backend with the
shared `api` client (`baseURL` `/api/v1`, cookies included).

### Replacing a core page

A route with the same `path` replaces the core page; `index: true` replaces
Home. Core paths: `index` (Home), `documents`, `users`, `roles`, `permissions`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

The simplest way is to copy the core page into `custom/`, edit the copy, and
register it under the same path. Your copy does not receive upstream fixes to
that page, so compare it with core after updates.

### Sidebar links

`nav` items are added after the core ones. An item with the same `to` replaces
the core link, for example to rename it or require another permission:

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

### Translations

- New keys must start with `custom.`, for example `custom.crm.title`.
- Core keys can be overridden, for example `"nav.documents": "Files"`.
- Languages: `en`, `es`, `uk`, `tr`, `fr`. A missing key falls back to `en`,
  then to the key itself.
- The interface uses the system language chosen in `uv run setup`
  (`APP_LANGUAGE` in `backend/.env`).

### Themes

A theme is a set of CSS variables under `[data-theme="<id>"]` plus an entry in
`themes`. Put both in your `custom/` folder; upstream never touches them.

```css
/* frontend/src/custom/brand/ocean.css */
[data-theme="ocean"] {
  --background: #ecfeff;
  --foreground: #083344;
  --primary: #0e7490;
  --primary-foreground: #ffffff;
  --ring: #0e7490;
  /* any variable from :root in frontend/src/index.css */
}

[data-theme="ocean"] .app-header {
  background-color: var(--primary);
  color: var(--primary-foreground);
}
```

```tsx
// frontend/src/custom/brand/index.ts
import type {Extension} from "@/extensions";
import "./ocean.css";

export default {
    themes: [
        {id: "ocean", labelKey: "custom.theme.ocean"},
        {id: "graphite", labelKey: "custom.theme.graphite", dark: true},
    ],
    defaultTheme: "ocean",
    messages: {
        en: {"custom.theme.ocean": "Ocean", "custom.theme.graphite": "Graphite"},
    },
} satisfies Extension;
```

- `id` is the value of `data-theme` on `<html>`. Style it only in your CSS file,
  imported from the extension module.
- The full variable list (`--background`, `--primary`, `--sidebar`, `--success`,
  …) is in `:root` of `frontend/src/index.css`. Variables you do not set keep
  the core values.
- `dark: true` adds the `.dark` class and a dark color scheme for browser
  controls.
- A theme with the same `id` as a core one (`neutral`, `slate`, `midnight`) replaces its
  label and options; your CSS for it loads after core CSS and wins.
- `defaultTheme` applies to users who have not picked a theme yet; a choice
  saved in the browser is kept.

## What you can safely import

These modules are kept backward compatible, and breaking changes are listed in
release notes:

- Backend: `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`
- Frontend: `@/extensions`, `@/shared/*`, `@/components/ui/*`

Anything else (services, internal parts of core pages) may change between
versions.

## Limitations

These still require editing core files:

- The header, the overall layout, the login page and other pages outside the
  logged-in layout
- Hiding a core sidebar link (you can replace it, not remove it)
- Adding a part to a core page (a column, a button) without replacing the page
- The chat assistant's system prompt and the document processing pipeline
  (endpoints can be replaced, internal steps cannot)
