# Customizing Corpus

This guide shows you how to add pages, API endpoints, permissions, themes and
translations to Corpus without editing core files, so updates keep merging
cleanly.

Other languages: [Español](es.md) · [Français](fr.md)

## About extensions

Your changes live in two folders. Updates never ship files there, so pulling a
new version merges without conflicts.

| Folder | What goes there |
|---|---|
| `backend/src/custom/EXTENSION/` | Python packages: API endpoints, models, permissions, background tasks |
| `backend/src/custom/migrations/` | Your Alembic migrations |
| `frontend/src/custom/EXTENSION/index.ts(x)` | Pages, sidebar links, translations, themes |

Replace EXTENSION with any folder name you choose, for example `crm` or `hr`.
You can have several extensions. They load in alphabetical order, and folders
whose names start with `_` are skipped. You do not register them anywhere:
Corpus finds both folders automatically.

You can still edit core files, but each edit may conflict with the next
update. Use an extension first, and edit core only when there is no extension
point for your change. See [Limitations](#limitations).

## What you can import

These modules stay backward compatible, and their breaking changes are listed
in the release notes:

* Backend: `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`, `services.audit`
* Frontend: `@/extensions`, `@/shared/*`, `@/components/ui/*`

Anything else, such as services or the internal parts of core pages, may
change between versions.

## Backend extension points

A package `backend/src/custom/EXTENSION/__init__.py` can define any of these:

| Name | What it does |
|---|---|
| `router` | An `APIRouter` mounted under `/api/v1` **before** the core routers |
| `PERMISSIONS` | `((key, name, description), ...)`, seeded together with the core permissions |
| `setup(app)` | A function called once with the FastAPI app at startup |
| Models | Any SQLAlchemy model the package imports is visible to Alembic |
| `tasks.py` | A module the Celery worker loads, if it exists |
| `CORE_API` | The extension API version the package was written for, now `1`. A package written for another version is skipped, with an error in the log |

## Adding API endpoints

1. Write the router:

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

2. Export it from the package:

   ```python
   # backend/src/custom/crm/__init__.py
   from .api import router
   ```

The endpoint is served at `/api/v1/crm/hello`. Follow the project rules for
authentication and errors: use `Depends(get_current_user)` or
`require_permission(...)`, and raise `AppError(code, message, status_code)`
from `exceptions`.

## Replacing a core endpoint

Custom routers are mounted first, so a route with the same method and path
wins. This replaces `GET /api/v1/users`:

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Keep the response shape that the core frontend expects, or replace the page
too.

## Adding permissions

1. Declare the permissions. Use `resource.action` keys that do not collide with
   core resources.

   ```python
   # backend/src/custom/crm/__init__.py
   PERMISSIONS = (
       ("crm.report", "CRM report", "View the CRM report"),
   )
   ```

2. Seed them:

   ```sh
   cd backend/src && uv run python -m seeders.run
   ```

The permissions then appear on the **Permissions** page and can be assigned to
roles. The Admin role receives them automatically.

## Running code at startup

`setup(app)` can add middleware and exception handlers, or replace any
dependency that core injects with `Depends(...)`:

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

An entry in `app.dependency_overrides` replaces that dependency everywhere at
once.

## Storing your own data

Do not add columns to core tables such as `users`. Put your data in your own
table with a one-to-one key, so core can change its tables freely.

1. Define the model. Prefix the table name with `custom_` to avoid clashes with
   future core tables.

   ```python
   # backend/src/custom/crm/models.py
   from sqlalchemy import ForeignKey, String
   from sqlalchemy.orm import Mapped, mapped_column, relationship

   from database import Base
   from models import User


   class UserProfile(Base):
       __tablename__ = "custom_user_profiles"

       user_id: Mapped[int] = mapped_column(
           ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
       )
       phone: Mapped[str | None] = mapped_column(String(32))
       user: Mapped[User] = relationship(backref="profile")  # user.profile works too
   ```

2. Import the module in the package, so Alembic sees the table:

   ```python
   # backend/src/custom/crm/__init__.py
   from . import models  # noqa: F401
   from .api import router
   ```

3. Create a migration. See [Creating migrations](#creating-migrations).

Tables that are not linked to users work the same way.

## Creating migrations

Custom migrations are on their own Alembic branch, `custom`, so core
migrations never collide with them.

1. Bring the database up to date:

   ```sh
   cd backend
   uv run alembic upgrade heads
   mkdir -p src/custom/migrations
   ```

2. Generate the migration. For the first custom migration only, start the
   `custom` branch after the core head:

   ```sh
   uv run alembic revision --autogenerate -m "crm profiles" \
     --head base --branch-label custom --version-path src/custom/migrations \
     --depends-on $(uv run alembic heads | awk '{print $1; exit}')
   ```

   For every later migration:

   ```sh
   uv run alembic revision --autogenerate -m "MESSAGE" --head custom@head
   ```

3. Check the generated file, then apply it:

   ```sh
   uv run alembic upgrade heads
   ```

Always use `upgrade heads`, plural: it applies both the core and the custom
branch.

## Adding background tasks

Write a Celery task in `tasks.py` of your package. Prefix its `name` with your
extension name to avoid collisions.

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Start it from your endpoint with `sync.delay()`.

## Recording audit entries

Record your own actions with `AuditService` from `Depends(get_audit_service)`
in `api.deps`:

```python
audit.record("crm.export", actor=user, target_label=...)
```

The entries appear on the **Audit log** page under their action name. Never
record passwords, tokens or other secrets.

## Frontend extension points

A file `frontend/src/custom/EXTENSION/index.tsx` default-exports an
`Extension`. The type is in `frontend/src/extensions.ts`.

| Field | What it does |
|---|---|
| `routes` | Pages inside the signed-in layout, with the header and sidebar |
| `nav` | Sidebar links, after the core ones |
| `messages` | Translations per language |
| `themes` | Extra themes in the theme picker |
| `defaultTheme` | The theme for users who have not picked one |
| `coreApi` | The extension API version the module was written for, now `1`. A module written for another version is skipped, with an error in the browser console |

## Adding a page

1. Write the page:

   ```tsx
   // frontend/src/custom/crm/Report.tsx
   import {useI18n} from "@/shared/i18n/I18nProvider";

   export function Report() {
       const {t} = useI18n();
       return <h1>{t("custom.crm.title")}</h1>;
   }
   ```

2. Register it with a sidebar link and its translations:

   ```tsx
   // frontend/src/custom/crm/index.tsx
   import type {Extension} from "@/extensions";
   import {Report} from "./Report";

   export default {
       routes: [{path: "crm", Component: Report, handle: {can: "crm.report"}}],
       nav: [{to: "/crm", labelKey: "custom.crm.title", end: true, can: "crm.report"}],
       messages: {
           en: {"custom.crm.title": "CRM report"},
           fr: {"custom.crm.title": "Rapport CRM"},
       },
   } satisfies Extension;
   ```

`can` hides the link from users without that permission. To also block the page
itself, add `handle: {can: "crm.report"}` to the route: users without the
permission see the not-found page. Inside a page, use
`can("crm.report")` from `@/shared/lib/api/me`. Call your backend with the
shared `api` client: its base URL is `/api/v1`, and it sends the session
cookies.

## Replacing a core page

A route with the same `path` replaces the core page, and `index: true`
replaces Home. The core paths are `index` (Home), `documents`, `users`,
`users/:userId`, `roles`, `permissions`, `feedback`, `chat-history`,
`chat-history/:conversationId`, `account`, `audit`, `system` and `errors`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

The simplest way is to copy the core page into `custom/`, edit the copy, and
register it under the same path. Your copy does not receive core fixes to
that page, so compare it with core after updates.

## Changing sidebar links

`nav` items are added after the core ones. An item with the same `to`
replaces the core link, for example to rename it or to require another
permission:

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

## Adding translations

* New keys must start with `custom.`, for example `custom.crm.title`.
* You can override core keys, for example `"nav.documents": "Files"`.
* The languages are `en`, `es` and `fr`. A missing key falls back to `en`,
  then to the key itself.
* The interface uses the languages chosen in `uv run install` or
  `uv run configure` (`APP_LANGUAGE`, the default, and `APP_LANGUAGES`, which
  users switch between in the header, in `backend/.env`). Give your keys a
  value for each of them.

## Adding themes

A theme is a set of CSS variables under `[data-theme="THEME-ID"]` plus an
entry in `themes`. Keep both in your `custom/` folder.

1. Write the CSS. Replace THEME-ID with your theme's ID, here `ocean`:

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

2. Register the theme and import the CSS:

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

Theme options:

* `id` is the value of `data-theme` on `<html>`. Style it only in your CSS
  file, imported from the extension module.
* The full variable list (`--background`, `--primary`, `--sidebar`,
  `--success` and others) is in `:root` of `frontend/src/index.css`. Variables
  you do not set keep the core values.
* `dark: true` adds the `.dark` class and a dark color scheme for browser
  controls.
* A theme with the same `id` as a core theme (`neutral`, `ledger`, `slate`,
  `midnight`) replaces its label and options. Your CSS loads after the core
  CSS and wins.
* `defaultTheme` applies to users who have not picked a theme yet. A choice
  saved in the browser is kept.

## Getting updates

1. Add the main repository once. Replace UPSTREAM-URL with its address.

   ```sh
   git remote add upstream UPSTREAM-URL
   ```

2. Pull the update, apply the migrations of core and of your extensions, and
   seed new permissions:

   ```sh
   git pull upstream main
   cd backend && uv run alembic upgrade heads
   cd src && uv run python -m seeders.run
   ```

3. Restart the backend, the Celery worker and the frontend dev server.

## Limitations

These changes still require editing core files:

* The header, the overall layout, the sign-in page and other pages outside the
  signed-in layout
* Hiding a core sidebar link. You can replace a link, but not remove it.
* Adding a part to a core page, such as a column or a button, without
  replacing the whole page
* The chat assistant's system prompt and the document processing pipeline.
  You can replace endpoints, but not their internal steps.
