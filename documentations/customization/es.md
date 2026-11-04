# Personalizar Archfold

Esta guía muestra cómo añadir páginas, endpoints de API, permisos, temas y
traducciones an Archfold sin editar archivos del núcleo, para que las
actualizaciones se integren sin conflictos.

Otros idiomas: [English](en.md) · [Français](fr.md)

## Acerca de las extensiones

Sus cambios viven en dos carpetas. Las actualizaciones nunca incluyen archivos
en ellas, así que una nueva versión se integra sin conflictos.

| Carpeta | Qué va ahí |
|---|---|
| `backend/src/custom/EXTENSION/` | Paquetes Python: endpoints de API, modelos, permisos, tareas en segundo plano |
| `backend/src/custom/migrations/` | Sus migraciones de Alembic |
| `frontend/src/custom/EXTENSION/index.ts(x)` | Páginas, enlaces de la barra lateral, traducciones, temas |

Sustituya EXTENSION por cualquier nombre de carpeta, por ejemplo `crm` o `hr`.
Puede tener varias extensiones. Se cargan en orden alfabético y se omiten las
carpetas cuyo nombre empieza por `_`. No hay que registrarlas en ningún sitio:
Archfold encuentra ambas carpetas automáticamente.

Puede seguir editando archivos del núcleo, pero cada edición puede causar un
conflicto en la próxima actualización. Use primero una extensión y edite el
núcleo solo cuando no exista un punto de extensión para su cambio. Vea
[Limitaciones](#limitaciones).

## Qué puede importar

Estos módulos se mantienen compatibles con versiones anteriores, y sus cambios
incompatibles se indican en las notas de la versión:

* Backend: `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`, `services.audit`
* Frontend: `@/extensions`, `@/shared/*`, `@/components/ui/*`

Todo lo demás, como los servicios o las partes internas de las páginas del
núcleo, puede cambiar entre versiones.

## Puntos de extensión del backend

Un paquete `backend/src/custom/EXTENSION/__init__.py` puede definir cualquiera
de estos:

| Nombre | Qué hace |
|---|---|
| `router` | Un `APIRouter` montado en `/api/v1` **antes** que los routers del núcleo |
| `PERMISSIONS` | `((key, name, description), ...)`, sembrados junto con los permisos del núcleo |
| `setup(app)` | Una función que se llama una vez con la app de FastAPI al arrancar |
| Modelos | Alembic ve cualquier modelo de SQLAlchemy que importe el paquete |
| `tasks.py` | Un módulo que carga el worker de Celery, si existe |
| `CORE_API` | La versión de la API de extensiones para la que se escribió el paquete, ahora `2`. Un paquete escrito para otra versión se omite, con un error en el registro |

## Añadir endpoints de API

1. Escriba el router:

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

2. Expórtelo desde el paquete:

   ```python
   # backend/src/custom/crm/__init__.py
   from .api import router
   ```

El endpoint queda disponible en `/api/v1/crm/hello`. Siga las reglas del
proyecto para la autenticación y los errores: use `Depends(get_current_user)`
o `require_permission(...)`, y lance `AppError(code, message, status_code)` de
`exceptions`.

## Reemplazar un endpoint del núcleo

Los routers personalizados se montan primero, así que una ruta con el mismo
método y la misma ruta gana. Esto reemplaza `GET /api/v1/users`:

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Mantenga la forma de la respuesta que espera el frontend del núcleo, o
reemplace también la página.

## Añadir permisos

1. Declare los permisos. Use claves `recurso.acción` que no coincidan con los
   recursos del núcleo.

   ```python
   # backend/src/custom/crm/__init__.py
   PERMISSIONS = (
       ("crm.report", "Informe CRM", "Ver el informe CRM"),
   )
   ```

2. Siémbrelos:

   ```sh
   cd backend/src && uv run python -m seeders.run
   ```

Los permisos aparecen entonces en la página **Permisos** y se pueden asignar a
roles. El rol Admin los recibe automáticamente.

## Ejecutar código al arrancar

`setup(app)` puede añadir middleware y manejadores de excepciones, o
reemplazar cualquier dependencia que el núcleo inyecta con `Depends(...)`:

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

Una entrada en `app.dependency_overrides` reemplaza esa dependencia en todas
partes a la vez.

## Guardar sus propios datos

No añada columnas a tablas del núcleo como `users`. Guarde sus datos en su
propia tabla con una clave uno a uno, para que el núcleo pueda cambiar sus
tablas libremente.

1. Defina el modelo. Empiece el nombre de la tabla por `custom_` para evitar
   conflictos con futuras tablas del núcleo.

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
       user: Mapped[User] = relationship(backref="profile")  # user.profile también funciona
   ```

2. Importe el módulo en el paquete para que Alembic vea la tabla:

   ```python
   # backend/src/custom/crm/__init__.py
   from . import models  # noqa: F401
   from .api import router
   ```

3. Cree una migración. Vea [Crear migraciones](#crear-migraciones).

Las tablas no vinculadas a usuarios funcionan igual.

## Crear migraciones

Las migraciones personalizadas están en su propia rama de Alembic, `custom`,
así que las migraciones del núcleo nunca chocan con ellas.

1. Ponga la base de datos al día:

   ```sh
   cd backend
   uv run alembic upgrade heads
   mkdir -p src/custom/migrations
   ```

2. Genere la migración. Solo para la primera migración personalizada, inicie la
   rama `custom` después del head del núcleo:

   ```sh
   uv run alembic revision --autogenerate -m "crm profiles" \
     --head base --branch-label custom --version-path src/custom/migrations \
     --depends-on $(uv run alembic heads | awk '{print $1; exit}')
   ```

   Para cada migración posterior:

   ```sh
   uv run alembic revision --autogenerate -m "MESSAGE" --head custom@head
   ```

3. Revise el archivo generado y aplíquelo:

   ```sh
   uv run alembic upgrade heads
   ```

Use siempre `upgrade heads`, en plural: aplica tanto la rama del núcleo como
la personalizada.

## Añadir tareas en segundo plano

Escriba una tarea de Celery en `tasks.py` de su paquete. Empiece su `name` por
el nombre de su extensión para evitar colisiones.

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Láncela desde su endpoint con `sync.delay()`.

## Registrar entradas de auditoría

Registre sus propias acciones con `AuditService` de
`Depends(get_audit_service)` en `api.deps`:

```python
audit.record("crm.export", actor=user, target_label=...)
```

Las entradas aparecen en la página **Registro de auditoría** con el nombre de
su acción. No registre nunca contraseñas, tokens ni otros secretos.

## Puntos de extensión del frontend

Un archivo `frontend/src/custom/EXTENSION/index.tsx` exporta por defecto una
`Extension`. El tipo está en `frontend/src/extensions.ts`.

| Campo | Qué hace |
|---|---|
| `routes` | Páginas dentro del diseño con sesión iniciada, con cabecera y barra lateral |
| `nav` | Enlaces de la barra lateral, después de los del núcleo |
| `messages` | Traducciones por idioma |
| `themes` | Temas adicionales en el selector de temas |
| `defaultTheme` | El tema para los usuarios que no han elegido ninguno |
| `coreApi` | La versión de la API de extensiones para la que se escribió el módulo, ahora `2`. Un módulo escrito para otra versión se omite, con un error en la consola del navegador |

## Añadir una página

1. Escriba la página:

   ```tsx
   // frontend/src/custom/crm/Report.tsx
   import {useI18n} from "@/shared/i18n/I18nProvider";

   export function Report() {
       const {t} = useI18n();
       return <h1>{t("custom.crm.title")}</h1>;
   }
   ```

2. Regístrela con un enlace en la barra lateral y sus traducciones:

   ```tsx
   // frontend/src/custom/crm/index.tsx
   import type {Extension} from "@/extensions";
   import {Report} from "./Report";

   export default {
       routes: [{path: "crm", Component: Report, handle: {can: "crm.report"}}],
       nav: [{to: "/crm", labelKey: "custom.crm.title", end: true, can: "crm.report"}],
       messages: {
           en: {"custom.crm.title": "CRM report"},
           es: {"custom.crm.title": "Informe CRM"},
       },
   } satisfies Extension;
   ```

`can` oculta el enlace a los usuarios sin ese permiso. Para bloquear también la
página, añada `handle: {can: "crm.report"}` a la ruta: los usuarios sin el
permiso ven la página de no encontrado. Dentro de una página,
use `can("crm.report")` de `@/shared/lib/api/me`. Llame a su backend con el
cliente compartido `api`: su URL base es `/api/v1` y envía las cookies de
sesión.

## Reemplazar una página del núcleo

Una ruta con el mismo `path` reemplaza la página del núcleo, e `index: true`
reemplaza el Inicio. Las rutas del núcleo son `index` (Inicio), `documents`,
`users`, `users/:userId`, `roles`, `permissions`, `feedback`, `chat-history`,
`chat-history/:conversationId`, `account`, `audit`, `system` y `errors`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

Lo más sencillo es copiar la página del núcleo en `custom/`, editar la copia y
registrarla con la misma ruta. Su copia no recibe las correcciones del núcleo
para esa página, así que compárela con el núcleo tras cada actualización.

## Cambiar enlaces de la barra lateral

Los elementos de `nav` se añaden después de los del núcleo. Un elemento con el
mismo `to` reemplaza el enlace del núcleo, por ejemplo para renombrarlo o
exigir otro permiso:

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

## Añadir traducciones

* Las claves nuevas deben empezar por `custom.`, por ejemplo
  `custom.crm.title`.
* Puede sobrescribir claves del núcleo, por ejemplo
  `"nav.documents": "Archivos"`.
* Los idiomas son `en`, `es` y `fr`. Una clave que falta usa `en` y, si
  tampoco existe, la propia clave.
* La interfaz usa los idiomas elegidos en `uv run install` o
  `uv run configure` (`APP_LANGUAGE`, el predeterminado, y `APP_LANGUAGES`,
  entre los que los usuarios cambian en la cabecera, en `backend/.env`). Dé
  un valor a sus claves en cada uno de ellos.

## Añadir temas

La interfaz está hecha con [daisyUI](https://daisyui.com/). Un tema es un
conjunto de variables CSS de daisyUI bajo `[data-theme="THEME-ID"]` más una
entrada en `themes`. Guarde ambos en su carpeta `custom/`. Los temas del núcleo son
`corporate` y `business` (modo oscuro), con un botón claro/oscuro en la cabecera.
Al añadir un tema, el botón se convierte en un menú de temas.

### Usar un tema ya hecho

daisyUI incluye [35 temas](https://daisyui.com/docs/themes/). Importe uno y
regístrelo. Aquí, THEME-ID es `emerald`:

```ts
// frontend/src/custom/brand/index.ts
import type {Extension} from "@/extensions";
import "daisyui/theme/emerald.css";

export default {
    themes: [{id: "emerald", labelKey: "custom.theme.emerald"}],
    defaultTheme: "emerald",
    messages: {en: {"custom.theme.emerald": "Emerald"}},
} satisfies Extension;
```

Algunos de estos temas tienen menos contraste de texto que el tema del núcleo.
Compruébelos antes de usar uno como predeterminado.

### Escribir su propio tema

1. Elija sus colores en el
   [generador de temas de daisyUI](https://daisyui.com/theme-generator/) y copie
   las variables en un archivo CSS. Sustituya THEME-ID por el ID de su tema, aquí
   `ocean`:

   ```css
   /* frontend/src/custom/brand/ocean.css */
   [data-theme="ocean"] {
     color-scheme: light;
     --color-base-100: #ecfeff;
     --color-base-200: #cffafe;
     --color-base-300: #a5f3fc;
     --color-base-content: #083344;
     --color-primary: #0e7490;
     --color-primary-content: #ffffff;
     --radius-box: 0.5rem;
   }
   ```

2. Registre el tema e importe el CSS:

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

Opciones del tema:

* `id` es el valor de `data-theme` en `<html>`. Aplique estilos solo en su
  archivo CSS, importado desde el módulo de la extensión.
* Las variables aparecen en la
  [documentación de daisyUI](https://daisyui.com/docs/themes/). Las que no
  defina conservan los valores del tema predeterminado del núcleo, `corporate`.
* `dark: true` añade la clase `.dark` y un esquema de color oscuro para los
  controles del navegador. En su CSS, defina también `color-scheme: dark`.
* Un tema con el ID de un tema del núcleo reemplaza su etiqueta y sus opciones. Su CSS se carga después del CSS del núcleo y prevalece.
* `defaultTheme` se aplica a los usuarios que aún no han elegido un tema (sin
  él, tienen `corporate`). Una elección guardada en el navegador se mantiene.
* En un tema oscuro, haga `--color-base-300` más claro que `--color-base-100`:
  los bordes lo usan. Muchos temas oscuros ya hechos lo tienen más oscuro, y los
  bordes apenas se ven hasta que lo redefine.
* Incluya en la compilación las fuentes que use su tema, por ejemplo con un
  paquete `@fontsource`. Archfold no carga fuentes de internet.

## Obtener actualizaciones

1. Añada el repositorio principal una vez:

   ```sh
   git remote add upstream https://github.com/deformator852/archfold.git
   ```

2. Descargue la actualización, aplique las migraciones del núcleo y de sus
   extensiones, y siembre los permisos nuevos:

   ```sh
   git pull upstream main
   cd backend && uv run alembic upgrade heads
   cd src && uv run python -m seeders.run
   ```

3. Reinicie el backend, el worker de Celery y el servidor de desarrollo del
   frontend.

## Limitaciones

Estos cambios todavía requieren editar archivos del núcleo:

* La cabecera, el diseño general, la página de inicio de sesión y otras
  páginas fuera del diseño con sesión iniciada
* Ocultar un enlace del núcleo en la barra lateral. Puede reemplazarlo, pero
  no quitarlo.
* Añadir una parte a una página del núcleo, como una columna o un botón, sin
  reemplazar la página entera
* El prompt de sistema del asistente y el flujo de procesamiento de
  documentos. Puede reemplazar endpoints, pero no sus pasos internos.
