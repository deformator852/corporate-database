# Özelleştirme

Diğer diller: [English](en.md) · [Español](es.md) · [Українська](uk.md) · [Français](fr.md)

## Nasıl çalışır

Tüm değişiklikleriniz iki klasörde durur. Upstream güncellemeleri bu klasörlere
hiçbir zaman dosya eklemez, bu yüzden yeni sürüm çakışma olmadan birleşir:

| Klasör | İçeriği |
|---|---|
| `backend/src/custom/<name>/` | Python paketleri: API uç noktaları, modeller, izinler, arka plan görevleri |
| `backend/src/custom/migrations/` | Kendi Alembic migrasyonlarınız |
| `frontend/src/custom/<name>/index.ts(x)` | Sayfalar, kenar çubuğu bağlantıları, çeviriler, temalar |

`<name>` istediğiniz herhangi bir addır (`crm`, `hr`, …). Birden fazla
olabilir. Alfabetik sırayla yüklenirler; `_` ile başlayan klasörler atlanır.
Çekirdek dosyalarda hiçbir şeyi kaydetmeniz gerekmez: iki klasör de otomatik
olarak bulunur.

Çekirdek dosyaları yine de düzenleyebilirsiniz, ancak her düzenleme bir sonraki
güncellemede çakışmaya yol açabilir. Önce bir eklenti kullanın; çekirdeği yalnızca
ihtiyacınız için bir genişletme noktası yoksa düzenleyin (bkz.
[Sınırlamalar](#sınırlamalar)).

## Güncellemeleri almak

```sh
git remote add upstream <upstream repo url>   # bir kez
git pull upstream main
cd backend && uv run alembic upgrade heads     # "heads": çekirdek + custom dalları
cd src && uv run python -m seeders.run         # yeni çekirdek ve custom izinleri
```

Ardından backend'i, Celery worker'ı ve frontend geliştirme sunucusunu yeniden
başlatın.

## Backend

`backend/src/custom/<name>/__init__.py` paketi bunlardan herhangi birini
tanımlayabilir:

| Ad | Ne yapar |
|---|---|
| `router` | `/api/v1` altına çekirdek router'lardan **önce** bağlanan `APIRouter` |
| `PERMISSIONS` | `((key, name, description), ...)`, çekirdek izinlerle birlikte oluşturulur |
| `setup(app)` | Başlangıçta FastAPI uygulamasıyla bir kez çağrılır |
| modeller | Paketin içe aktardığı her SQLAlchemy modeli Alembic tarafından görülür |
| `tasks.py` | Varsa Celery worker tarafından yüklenir |

### Yeni API uç noktaları

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

Uç nokta `/api/v1/crm/hello` adresinde çalışır. Kimlik doğrulama ve hatalar için
proje kurallarına uyun: `Depends(get_current_user)` /
`require_permission(...)` ve `exceptions` içinden
`raise AppError(code, message, status_code)`.

### Çekirdek uç noktasını değiştirmek

Custom router'lar önce bağlanır, bu yüzden aynı yöntem ve yola sahip rota
kazanır. Bu, `GET /api/v1/users` uç noktasını değiştirir:

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Çekirdek frontend'in beklediği yanıt biçimini koruyun ya da sayfayı da
değiştirin.

### İzinler

```python
# backend/src/custom/crm/__init__.py
PERMISSIONS = (
    ("crm.report", "CRM report", "View the CRM report"),
)
```

`seeders.run` sonrasında izin listesinde görünürler ve rollere atanabilirler.
Admin rolü bunları otomatik olarak alır. Çekirdek kaynaklarla çakışmayan
`resource.action` anahtarları kullanın.

### `setup(app)`: geçersiz kılmalar, middleware, işleyiciler

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

`app.dependency_overrides`, çekirdeğin `Depends(...)` ile enjekte ettiği herhangi
bir fonksiyonu her yerde birden değiştirir.

### Modeller ve ek kullanıcı verileri

`users` gibi çekirdek tablolara sütun eklemeyin. Verilerinizi bire bir anahtarla
bağlı kendi tablonuzda tutun. Böylece çekirdek kendi tablolarını serbestçe
değiştirebilir.

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

Bağımsız tablolar (kullanıcılara bağlı olmayanlar) da aynı şekilde çalışır.

### Migrasyonlar

Custom migrasyonlar kendi Alembic dallarında (`custom`) durur, bu yüzden çekirdek
migrasyonlar onlarla hiçbir zaman çakışmaz.

```sh
cd backend
uv run alembic upgrade heads          # önce veritabanı güncel olmalı
mkdir -p src/custom/migrations

# yalnızca ilk custom migrasyon: çekirdek head'inden sonra "custom" dalını başlatır
uv run alembic revision --autogenerate -m "crm profiles" \
  --head base --branch-label custom --version-path src/custom/migrations \
  --depends-on $(uv run alembic heads | awk '{print $1; exit}')

# sonraki her biri
uv run alembic revision --autogenerate -m "..." --head custom@head

uv run alembic upgrade heads
```

Her zaman `upgrade heads` (çoğul) kullanın. Oluşturulan her dosyayı uygulamadan
önce kontrol edin.

### Arka plan görevleri (Celery)

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Uç noktanızdan `sync.delay()` ile çağırın. Çakışmaları önlemek için `name`
değerine eklentinizin önekini verin.

## Frontend

`frontend/src/custom/<name>/index.tsx` dosyası varsayılan olarak bir `Extension`
dışa aktarır (tip `frontend/src/extensions.ts` içinde):

| Alan | Ne yapar |
|---|---|
| `routes` | Oturum açmış kullanıcı düzeni içindeki sayfalar (üst bar + kenar çubuğu) |
| `nav` | Kenar çubuğu bağlantıları, çekirdek bağlantılardan sonra |
| `messages` | Dile göre çeviriler |
| `themes` | Tema seçicide ek temalar |
| `defaultTheme` | Henüz tema seçmemiş kullanıcılar için tema |

### Kenar çubuğu bağlantılı yeni sayfa

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
        tr: {"custom.crm.title": "CRM raporu"},
    },
} satisfies Extension;
```

`can`, bu izne sahip olmayan kullanıcılardan bağlantıyı gizler. Sayfa içinde
`@/shared/lib/api/me` içindeki `can("crm.report")` fonksiyonunu kullanın.
Backend'inizi ortak `api` istemcisiyle çağırın (`baseURL` `/api/v1`, çerezler
dahil).

### Çekirdek sayfasını değiştirmek

Aynı `path` değerine sahip rota çekirdek sayfasının yerini alır; `index: true`
ana sayfanın yerini alır. Çekirdek yolları: `index` (ana sayfa), `documents`,
`users`, `roles`, `permissions`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

En kolayı çekirdek sayfasını `custom/` içine kopyalamak, kopyayı düzenlemek ve
aynı yol altında kaydetmektir. Kopyanız o sayfa için upstream düzeltmelerini
almaz; bu yüzden güncellemelerden sonra çekirdekle karşılaştırın.

### Kenar çubuğu bağlantıları

`nav` öğeleri çekirdek bağlantılardan sonra eklenir. Aynı `to` değerine sahip
öğe, çekirdek bağlantısının yerini alır; örneğin adını değiştirmek veya başka bir
izin istemek için:

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

### Çeviriler

- Yeni anahtarlar `custom.` ile başlamalıdır, örneğin `custom.crm.title`.
- Çekirdek anahtarları geçersiz kılınabilir, örneğin
  `"nav.documents": "Dosyalar"`.
- Diller: `en`, `es`, `uk`, `tr`, `fr`. Eksik anahtar önce `en` değerine, sonra
  anahtarın kendisine düşer.
- Arayüz, `uv run setup` sırasında seçilen sistem dilini kullanır
  (`backend/.env` içindeki `APP_LANGUAGE`).

### Temalar

Tema, `[data-theme="<id>"]` altındaki CSS değişkenleri ile `themes` içindeki bir
kayıttan oluşur. İkisini de `custom/` klasörünüze koyun; upstream bunlara hiçbir
zaman dokunmaz.

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

- `id`, `<html>` üzerindeki `data-theme` değeridir. Onu yalnızca eklenti
  modülünden içe aktarılan kendi CSS dosyanızda biçimlendirin.
- Değişkenlerin tam listesi (`--background`, `--primary`, `--sidebar`,
  `--success`, …) `frontend/src/index.css` dosyasındaki `:root` içindedir.
  Tanımlamadığınız değişkenler çekirdek değerlerini korur.
- `dark: true`, `.dark` sınıfını ve tarayıcı denetimleri için koyu renk
  şemasını ekler.
- Çekirdek temayla (`neutral`, `slate`, `midnight`) aynı `id` değerine sahip tema, onun
  adını ve seçeneklerini değiştirir; onun için yazdığınız CSS çekirdek CSS'ten
  sonra yüklenir ve öncelik kazanır.
- `defaultTheme`, henüz tema seçmemiş kullanıcılara uygulanır; tarayıcıda
  kaydedilmiş seçim korunur.

## Güvenle içe aktarabilecekleriniz

Bu modüller geriye dönük uyumlu tutulur ve uyumsuz değişiklikler sürüm
notlarında belirtilir:

- Backend: `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`
- Frontend: `@/extensions`, `@/shared/*`, `@/components/ui/*`

Geri kalan her şey (servisler, çekirdek sayfaların iç kısımları) sürümler arasında
değişebilir.

## Sınırlamalar

Bunlar için hâlâ çekirdek dosyaları düzenlemek gerekir:

- Üst bar, genel düzen, giriş sayfası ve oturum açmış kullanıcı düzeni dışındaki
  diğer sayfalar
- Çekirdek kenar çubuğu bağlantısını gizlemek (değiştirilebilir, kaldırılamaz)
- Sayfanın tamamını değiştirmeden çekirdek sayfaya bir parça (sütun, düğme)
  eklemek
- Sohbet asistanının sistem istemi ve belge işleme hattı (uç noktalar
  değiştirilebilir, iç adımlar değiştirilemez)
