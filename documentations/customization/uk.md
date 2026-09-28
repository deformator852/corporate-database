# Кастомізація

Інші мови: [English](en.md) · [Español](es.md) · [Türkçe](tr.md) · [Français](fr.md)

## Як це працює

Усі ваші зміни лежать у двох папках. Оновлення з upstream ніколи не додають туди
файлів, тому нова версія підтягується без конфліктів:

| Папка | Що туди класти |
|---|---|
| `backend/src/custom/<name>/` | Python-пакети: API-ендпоінти, моделі, дозволи, фонові задачі |
| `backend/src/custom/migrations/` | Ваші міграції Alembic |
| `frontend/src/custom/<name>/index.ts(x)` | Сторінки, посилання в бічній панелі, переклади, теми |

`<name>` — будь-яка назва (`crm`, `hr`, …). Їх може бути кілька. Вони
завантажуються в алфавітному порядку, папки, що починаються з `_`, пропускаються.
Нічого не треба реєструвати у файлах ядра: обидві папки знаходяться автоматично.

Файли ядра редагувати можна, але кожна така правка може дати конфлікт при
наступному оновленні. Спершу використовуйте розширення, а ядро змінюйте лише
тоді, коли для потрібного немає точки розширення (див. [Обмеження](#обмеження)).

## Отримання оновлень

```sh
git remote add upstream <upstream repo url>   # один раз
git pull upstream main
cd backend && uv run alembic upgrade heads     # "heads": гілки ядра + custom
cd src && uv run python -m seeders.run         # нові дозволи ядра та custom
```

Після цього перезапустіть backend, Celery worker і dev-сервер frontend.

## Backend

Пакет `backend/src/custom/<name>/__init__.py` може визначати будь-що з цього:

| Назва | Що робить |
|---|---|
| `router` | `APIRouter`, підключається під `/api/v1` **раніше** за роутери ядра |
| `PERMISSIONS` | `((key, name, description), ...)`, сідяться разом із дозволами ядра |
| `setup(app)` | Викликається один раз із FastAPI-застосунком під час старту |
| моделі | Будь-яка SQLAlchemy-модель, імпортована пакетом, видима для Alembic |
| `tasks.py` | Якщо є, завантажується Celery worker |

### Нові API-ендпоінти

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

Ендпоінт буде доступний за адресою `/api/v1/crm/hello`. Дотримуйтесь правил
проєкту щодо авторизації та помилок: `Depends(get_current_user)` /
`require_permission(...)` і `raise AppError(code, message, status_code)` з
`exceptions`.

### Заміна ендпоінта ядра

Роутери custom підключаються першими, тому маршрут із тим самим методом і шляхом
має пріоритет. Так замінюється `GET /api/v1/users`:

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Зберігайте формат відповіді, який очікує frontend ядра, або замініть і сторінку.

### Дозволи

```python
# backend/src/custom/crm/__init__.py
PERMISSIONS = (
    ("crm.report", "CRM report", "View the CRM report"),
)
```

Після `seeders.run` вони з'являються у списку дозволів, і їх можна призначати
ролям. Роль admin отримує їх автоматично. Використовуйте ключі
`resource.action`, які не перетинаються з ресурсами ядра.

### `setup(app)`: підміни, middleware, обробники

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

`app.dependency_overrides` підміняє будь-яку функцію, яку ядро впроваджує через
`Depends(...)`, одразу всюди.

### Моделі та додаткові дані користувача

Не додавайте колонки в таблиці ядра, наприклад `users`. Зберігайте свої дані у
власній таблиці зі зв'язком один до одного. Тоді ядро зможе вільно змінювати свої
таблиці.

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

Самостійні таблиці (не пов'язані з користувачами) працюють так само.

### Міграції

Міграції custom живуть на власній гілці Alembic — `custom`, тому міграції ядра з
ними не конфліктують.

```sh
cd backend
uv run alembic upgrade heads          # спершу актуальна база
mkdir -p src/custom/migrations

# лише перша міграція custom: створює гілку "custom" після head ядра
uv run alembic revision --autogenerate -m "crm profiles" \
  --head base --branch-label custom --version-path src/custom/migrations \
  --depends-on $(uv run alembic heads | awk '{print $1; exit}')

# кожна наступна
uv run alembic revision --autogenerate -m "..." --head custom@head

uv run alembic upgrade heads
```

Завжди використовуйте `upgrade heads` (у множині). Перевіряйте кожен
згенерований файл перед застосуванням.

### Фонові задачі (Celery)

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Викликайте її через `sync.delay()` зі свого ендпоінта. Давайте `name` з префіксом
свого розширення, щоб уникнути збігів.

### Журнал дій

Записуйте власні дії через `AuditService` з `Depends(get_audit_service)`
(`api.deps`): `audit.record("crm.export", actor=user, target_label=...)`. Вони
з'являються на сторінці журналу дій під своєю назвою дії. Ніколи не записуйте
паролі, токени чи інші секрети.

## Frontend

Файл `frontend/src/custom/<name>/index.tsx` експортує за замовчуванням
`Extension` (тип у `frontend/src/extensions.ts`):

| Поле | Що робить |
|---|---|
| `routes` | Сторінки всередині layout для залогінених (шапка + бічна панель) |
| `nav` | Посилання в бічній панелі, після посилань ядра |
| `messages` | Переклади для кожної мови |
| `themes` | Додаткові теми у виборі теми |
| `defaultTheme` | Тема для користувачів, які ще не обрали свою |

### Нова сторінка з посиланням у бічній панелі

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

`can` ховає посилання від користувачів без цього дозволу. Усередині сторінки
використовуйте `can("crm.report")` з `@/shared/lib/api/me`. Звертайтеся до свого
backend через спільний клієнт `api` (`baseURL` `/api/v1`, cookies передаються).

### Заміна сторінки ядра

Маршрут із тим самим `path` замінює сторінку ядра, `index: true` замінює головну.
Шляхи ядра: `index` (головна), `documents`, `users`, `roles`, `permissions`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

Найпростіше скопіювати сторінку ядра в `custom/`, змінити копію і зареєструвати
її під тим самим шляхом. Ваша копія не отримує виправлень цієї сторінки з
upstream, тому звіряйте її з ядром після оновлень.

### Посилання в бічній панелі

Елементи `nav` додаються після посилань ядра. Елемент із тим самим `to` замінює
посилання ядра, наприклад щоб перейменувати його або вимагати інший дозвіл:

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

### Переклади

- Нові ключі мають починатися з `custom.`, наприклад `custom.crm.title`.
- Ключі ядра можна перевизначити, наприклад `"nav.documents": "Файли"`.
- Мови: `en`, `es`, `uk`, `tr`, `fr`. Якщо ключа немає, береться `en`, а потім
  сам ключ.
- Інтерфейс використовує мову системи, обрану в `uv run setup`
  (`APP_LANGUAGE` у `backend/.env`).

### Теми

Тема — це набір CSS-змінних під `[data-theme="<id>"]` плюс запис у `themes`.
Покладіть обидва у свою папку `custom/`; upstream їх ніколи не змінює.

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

- `id` — значення атрибута `data-theme` на `<html>`. Стилізуйте його лише у
  своєму CSS-файлі, імпортованому з модуля розширення.
- Повний список змінних (`--background`, `--primary`, `--sidebar`, `--success`,
  …) — у `:root` файлу `frontend/src/index.css`. Змінні, які ви не задали,
  беруться з ядра.
- `dark: true` додає клас `.dark` і темну колірну схему для елементів браузера.
- Тема з тим самим `id`, що й у ядрі (`neutral`, `slate`, `midnight`), замінює її назву та
  параметри; ваш CSS для неї завантажується після CSS ядра й має пріоритет.
- `defaultTheme` застосовується до користувачів, які ще не обрали тему; вибір,
  збережений у браузері, лишається.

## Що можна безпечно імпортувати

Ці модулі зберігають зворотну сумісність, а несумісні зміни описуються в
примітках до релізу:

- Backend: `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`, `services.audit`
- Frontend: `@/extensions`, `@/shared/*`, `@/components/ui/*`

Усе інше (сервіси, внутрішні частини сторінок ядра) може змінюватися між
версіями.

## Обмеження

Для цього досі треба редагувати файли ядра:

- Шапка, загальний layout, сторінка входу та інші сторінки поза layout для
  залогінених
- Приховати посилання ядра в бічній панелі (його можна замінити, але не
  прибрати)
- Додати частину в сторінку ядра (колонку, кнопку), не замінюючи всю сторінку
- Системний промпт чат-асистента та конвеєр обробки документів (ендпоінти можна
  замінити, внутрішні кроки — ні)
