# Personalización

Otros idiomas: [English](en.md) · [Українська](uk.md) · [Türkçe](tr.md) · [Français](fr.md)

## Cómo funciona

Todos sus cambios viven en dos carpetas. Las actualizaciones de upstream nunca
incluyen archivos en ellas, así que una nueva versión se integra sin conflictos:

| Carpeta | Qué va ahí |
|---|---|
| `backend/src/custom/<name>/` | Paquetes Python: endpoints de API, modelos, permisos, tareas en segundo plano |
| `backend/src/custom/migrations/` | Sus migraciones de Alembic |
| `frontend/src/custom/<name>/index.ts(x)` | Páginas, enlaces de la barra lateral, traducciones, temas |

`<name>` es cualquier nombre que elija (`crm`, `hr`, …). Puede tener varios. Se
cargan en orden alfabético y se omiten las carpetas que empiezan por `_`. No hay
que registrar nada en archivos del núcleo: ambas carpetas se detectan
automáticamente.

Puede seguir editando archivos del núcleo, pero cada edición puede causar un
conflicto en la próxima actualización. Use primero una extensión y edite el
núcleo solo cuando no exista un punto de extensión para ello (vea
[Limitaciones](#limitaciones)).

## Obtener actualizaciones

```sh
git remote add upstream <upstream repo url>   # una vez
git pull upstream main
cd backend && uv run alembic upgrade heads     # "heads": ramas del núcleo + custom
cd src && uv run python -m seeders.run         # permisos nuevos del núcleo y custom
```

Después reinicie el backend, el worker de Celery y el servidor de desarrollo del
frontend.

## Backend

Un paquete `backend/src/custom/<name>/__init__.py` puede definir cualquiera de
estos:

| Nombre | Qué hace |
|---|---|
| `router` | `APIRouter` montado bajo `/api/v1` **antes** que los routers del núcleo |
| `PERMISSIONS` | `((key, name, description), ...)` sembrados junto con los permisos del núcleo |
| `setup(app)` | Se llama una vez con la aplicación FastAPI al arrancar |
| modelos | Cualquier modelo SQLAlchemy importado por el paquete es visible para Alembic |
| `tasks.py` | Si existe, lo carga el worker de Celery |

### Nuevos endpoints de API

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

El endpoint queda en `/api/v1/crm/hello`. Siga las reglas del proyecto para
autenticación y errores: `Depends(get_current_user)` / `require_permission(...)`
y `raise AppError(code, message, status_code)` desde `exceptions`.

### Reemplazar un endpoint del núcleo

Los routers custom se montan primero, así que una ruta con el mismo método y
path tiene prioridad. Esto reemplaza `GET /api/v1/users`:

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Mantenga el formato de respuesta que espera el frontend del núcleo, o reemplace
también la página.

### Permisos

```python
# backend/src/custom/crm/__init__.py
PERMISSIONS = (
    ("crm.report", "CRM report", "View the CRM report"),
)
```

Tras `seeders.run` aparecen en la lista de permisos y se pueden asignar a roles.
El rol admin los recibe automáticamente. Use claves `resource.action` que no
coincidan con recursos del núcleo.

### `setup(app)`: sustituciones, middleware, manejadores

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

`app.dependency_overrides` sustituye cualquier función que el núcleo inyecta con
`Depends(...)`, en todas partes a la vez.

### Modelos y datos adicionales del usuario

No añada columnas a tablas del núcleo como `users`. Guarde sus datos en su propia
tabla con una clave uno a uno. Así el núcleo puede cambiar sus tablas libremente.

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

Las tablas independientes (no vinculadas a usuarios) funcionan igual.

### Migraciones

Las migraciones custom están en su propia rama de Alembic, `custom`, así que las
migraciones del núcleo nunca chocan con ellas.

```sh
cd backend
uv run alembic upgrade heads          # primero la base de datos al día
mkdir -p src/custom/migrations

# solo la primera migración custom: crea la rama "custom" tras el head del núcleo
uv run alembic revision --autogenerate -m "crm profiles" \
  --head base --branch-label custom --version-path src/custom/migrations \
  --depends-on $(uv run alembic heads | awk '{print $1; exit}')

# cada una de las siguientes
uv run alembic revision --autogenerate -m "..." --head custom@head

uv run alembic upgrade heads
```

Use siempre `upgrade heads` (en plural). Revise cada archivo generado antes de
aplicarlo.

### Tareas en segundo plano (Celery)

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Llámela con `sync.delay()` desde su endpoint. Use un `name` con el prefijo de su
extensión para evitar colisiones.

### Registro de auditoría

Registre sus propias acciones con `AuditService` desde
`Depends(get_audit_service)` (`api.deps`):
`audit.record("crm.export", actor=user, target_label=...)`. Aparecen en la
página del registro con el nombre de la acción tal cual. Nunca registre
contraseñas, tokens ni otros secretos.

## Frontend

Un archivo `frontend/src/custom/<name>/index.tsx` exporta por defecto un
`Extension` (tipo en `frontend/src/extensions.ts`):

| Campo | Qué hace |
|---|---|
| `routes` | Páginas dentro del layout de usuarios autenticados (cabecera + barra lateral) |
| `nav` | Enlaces de la barra lateral, después de los del núcleo |
| `messages` | Traducciones por idioma |
| `themes` | Temas adicionales en el selector de temas |
| `defaultTheme` | Tema para usuarios que aún no han elegido uno |

### Nueva página con enlace en la barra lateral

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
        es: {"custom.crm.title": "Informe CRM"},
    },
} satisfies Extension;
```

`can` oculta el enlace a los usuarios sin ese permiso. Dentro de una página, use
`can("crm.report")` de `@/shared/lib/api/me`. Llame a su backend con el cliente
compartido `api` (`baseURL` `/api/v1`, con cookies).

### Reemplazar una página del núcleo

Una ruta con el mismo `path` reemplaza la página del núcleo; `index: true`
reemplaza la de inicio. Rutas del núcleo: `index` (inicio), `documents`,
`users`, `roles`, `permissions`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

Lo más sencillo es copiar la página del núcleo en `custom/`, editar la copia y
registrarla bajo el mismo path. Su copia no recibe las correcciones de upstream
para esa página, así que compárela con el núcleo tras cada actualización.

### Enlaces de la barra lateral

Los elementos de `nav` se añaden después de los del núcleo. Un elemento con el
mismo `to` reemplaza el enlace del núcleo, por ejemplo para renombrarlo o exigir
otro permiso:

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

### Traducciones

- Las claves nuevas deben empezar por `custom.`, por ejemplo `custom.crm.title`.
- Las claves del núcleo se pueden sobrescribir, por ejemplo
  `"nav.documents": "Archivos"`.
- Idiomas: `en`, `es`, `uk`, `tr`, `fr`. Si falta una clave se usa `en` y, si
  tampoco existe, la propia clave.
- La interfaz usa el idioma del sistema elegido en `uv run setup`
  (`APP_LANGUAGE` en `backend/.env`).

### Temas

Un tema es un conjunto de variables CSS bajo `[data-theme="<id>"]` más una
entrada en `themes`. Ponga ambos en su carpeta `custom/`; upstream nunca los
toca.

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

- `id` es el valor de `data-theme` en `<html>`. Dele estilo solo en su archivo
  CSS, importado desde el módulo de la extensión.
- La lista completa de variables (`--background`, `--primary`, `--sidebar`,
  `--success`, …) está en `:root` de `frontend/src/index.css`. Las variables que
  no defina conservan los valores del núcleo.
- `dark: true` añade la clase `.dark` y un esquema de color oscuro para los
  controles del navegador.
- Un tema con el mismo `id` que uno del núcleo (`neutral`, `slate`, `midnight`) reemplaza su
  etiqueta y opciones; su CSS para él se carga después del CSS del núcleo y
  tiene prioridad.
- `defaultTheme` se aplica a los usuarios que aún no han elegido tema; la
  elección guardada en el navegador se conserva.

## Qué se puede importar con seguridad

Estos módulos mantienen compatibilidad hacia atrás, y los cambios
incompatibles se indican en las notas de la versión:

- Backend: `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`, `services.audit`
- Frontend: `@/extensions`, `@/shared/*`, `@/components/ui/*`

Todo lo demás (servicios, partes internas de las páginas del núcleo) puede
cambiar entre versiones.

## Limitaciones

Esto todavía requiere editar archivos del núcleo:

- La cabecera, el layout general, la página de inicio de sesión y otras páginas
  fuera del layout de usuarios autenticados
- Ocultar un enlace del núcleo en la barra lateral (se puede reemplazar, no
  quitar)
- Añadir una parte a una página del núcleo (una columna, un botón) sin
  reemplazar la página
- El prompt de sistema del asistente de chat y el procesamiento de documentos
  (los endpoints se pueden reemplazar, los pasos internos no)
