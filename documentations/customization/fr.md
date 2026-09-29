# Personnalisation

Autres langues : [English](en.md) · [Español](es.md)

## Fonctionnement

Toutes vos modifications vivent dans deux dossiers. Les mises à jour upstream n'y
ajoutent jamais de fichiers, donc une nouvelle version se fusionne sans conflit :

| Dossier | Contenu |
|---|---|
| `backend/src/custom/<name>/` | Paquets Python : endpoints d'API, modèles, permissions, tâches en arrière-plan |
| `backend/src/custom/migrations/` | Vos migrations Alembic |
| `frontend/src/custom/<name>/index.ts(x)` | Pages, liens de la barre latérale, traductions, thèmes |

`<name>` est un nom de votre choix (`crm`, `hr`, …). Vous pouvez en avoir
plusieurs. Ils sont chargés par ordre alphabétique, et les dossiers commençant
par `_` sont ignorés. Rien n'est à déclarer dans les fichiers du noyau : les deux
dossiers sont détectés automatiquement.

Vous pouvez toujours modifier les fichiers du noyau, mais chaque modification
peut provoquer un conflit à la prochaine mise à jour. Utilisez d'abord une
extension, et ne modifiez le noyau que s'il n'existe pas de point d'extension
pour ce besoin (voir [Limites](#limites)).

## Récupérer les mises à jour

```sh
git remote add upstream <upstream repo url>   # une seule fois
git pull upstream main
cd backend && uv run alembic upgrade heads     # "heads" : branches du noyau + custom
cd src && uv run python -m seeders.run         # nouvelles permissions du noyau et custom
```

Redémarrez ensuite le backend, le worker Celery et le serveur de développement
du frontend.

## Backend

Un paquet `backend/src/custom/<name>/__init__.py` peut définir n'importe lequel
de ces éléments :

| Nom | Effet |
|---|---|
| `router` | `APIRouter` monté sous `/api/v1` **avant** les routeurs du noyau |
| `PERMISSIONS` | `((key, name, description), ...)` créées avec les permissions du noyau |
| `setup(app)` | Appelée une fois avec l'application FastAPI au démarrage |
| modèles | Tout modèle SQLAlchemy importé par le paquet est visible par Alembic |
| `tasks.py` | Chargé par le worker Celery s'il existe |

### Nouveaux endpoints d'API

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

L'endpoint est servi à `/api/v1/crm/hello`. Suivez les règles du projet pour
l'authentification et les erreurs : `Depends(get_current_user)` /
`require_permission(...)` et `raise AppError(code, message, status_code)` depuis
`exceptions`.

### Remplacer un endpoint du noyau

Les routeurs custom sont montés en premier : une route avec la même méthode et le
même chemin l'emporte. Ceci remplace `GET /api/v1/users` :

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Conservez le format de réponse attendu par le frontend du noyau, ou remplacez
aussi la page.

### Permissions

```python
# backend/src/custom/crm/__init__.py
PERMISSIONS = (
    ("crm.report", "CRM report", "View the CRM report"),
)
```

Après `seeders.run`, elles apparaissent dans la liste des permissions et peuvent
être attribuées aux rôles. Le rôle admin les reçoit automatiquement. Utilisez des
clés `resource.action` qui n'entrent pas en collision avec les ressources du
noyau.

### `setup(app)` : substitutions, middleware, gestionnaires

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

`app.dependency_overrides` remplace n'importe quelle fonction que le noyau
injecte avec `Depends(...)`, partout à la fois.

### Modèles et données utilisateur supplémentaires

N'ajoutez pas de colonnes aux tables du noyau comme `users`. Mettez vos données
dans votre propre table avec une clé un-à-un. Le noyau peut alors modifier ses
tables librement.

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

Les tables indépendantes (non liées aux utilisateurs) fonctionnent de la même
façon.

### Migrations

Les migrations custom sont sur leur propre branche Alembic, `custom`, donc les
migrations du noyau n'entrent jamais en conflit avec elles.

```sh
cd backend
uv run alembic upgrade heads          # d'abord une base à jour
mkdir -p src/custom/migrations

# première migration custom uniquement : crée la branche "custom" après le head du noyau
uv run alembic revision --autogenerate -m "crm profiles" \
  --head base --branch-label custom --version-path src/custom/migrations \
  --depends-on $(uv run alembic heads | awk '{print $1; exit}')

# chacune des suivantes
uv run alembic revision --autogenerate -m "..." --head custom@head

uv run alembic upgrade heads
```

Utilisez toujours `upgrade heads` (au pluriel). Relisez chaque fichier généré
avant de l'appliquer.

### Tâches en arrière-plan (Celery)

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Appelez-la avec `sync.delay()` depuis votre endpoint. Préfixez son `name` avec le
nom de votre extension pour éviter les collisions.

### Journal d'audit

Enregistrez vos propres actions avec `AuditService` depuis
`Depends(get_audit_service)` (`api.deps`) :
`audit.record("crm.export", actor=user, target_label=...)`. Elles apparaissent
dans la page du journal sous le nom brut de l'action. N'enregistrez jamais de
mots de passe, de jetons ou d'autres secrets.

## Frontend

Un fichier `frontend/src/custom/<name>/index.tsx` exporte par défaut une
`Extension` (type dans `frontend/src/extensions.ts`) :

| Champ | Effet |
|---|---|
| `routes` | Pages dans le layout des utilisateurs connectés (en-tête + barre latérale) |
| `nav` | Liens de la barre latérale, après ceux du noyau |
| `messages` | Traductions par langue |
| `themes` | Thèmes supplémentaires dans le sélecteur de thème |
| `defaultTheme` | Thème des utilisateurs qui n'en ont pas encore choisi |

### Nouvelle page avec un lien dans la barre latérale

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
        fr: {"custom.crm.title": "Rapport CRM"},
    },
} satisfies Extension;
```

`can` masque le lien aux utilisateurs qui n'ont pas cette permission. Dans une
page, utilisez `can("crm.report")` depuis `@/shared/lib/api/me`. Appelez votre
backend avec le client partagé `api` (`baseURL` `/api/v1`, cookies inclus).

### Remplacer une page du noyau

Une route avec le même `path` remplace la page du noyau ; `index: true` remplace
l'accueil. Chemins du noyau : `index` (accueil), `documents`, `users`, `roles`,
`permissions`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

Le plus simple est de copier la page du noyau dans `custom/`, de modifier la
copie et de l'enregistrer sous le même chemin. Votre copie ne reçoit pas les
correctifs upstream de cette page : comparez-la au noyau après chaque mise à
jour.

### Liens de la barre latérale

Les éléments de `nav` sont ajoutés après ceux du noyau. Un élément avec le même
`to` remplace le lien du noyau, par exemple pour le renommer ou exiger une autre
permission :

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

### Traductions

- Les nouvelles clés doivent commencer par `custom.`, par exemple
  `custom.crm.title`.
- Les clés du noyau peuvent être redéfinies, par exemple
  `"nav.documents": "Fichiers"`.
- Langues : `en`, `es`, `fr`. Une clé absente se rabat sur `en`,
  puis sur la clé elle-même.
- L'interface utilise la langue du système choisie dans `uv run setup`
  (`APP_LANGUAGE` dans `backend/.env`).

### Thèmes

Un thème est un ensemble de variables CSS sous `[data-theme="<id>"]` plus une
entrée dans `themes`. Placez les deux dans votre dossier `custom/` ; upstream
n'y touche jamais.

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

- `id` est la valeur de `data-theme` sur `<html>`. Stylez-le uniquement dans
  votre fichier CSS, importé depuis le module de l'extension.
- La liste complète des variables (`--background`, `--primary`, `--sidebar`,
  `--success`, …) se trouve dans `:root` de `frontend/src/index.css`. Les
  variables non définies gardent les valeurs du noyau.
- `dark: true` ajoute la classe `.dark` et un schéma de couleurs sombre pour les
  contrôles du navigateur.
- Un thème ayant le même `id` qu'un thème du noyau (`neutral`, `slate`, `midnight`) remplace
  son libellé et ses options ; votre CSS pour lui est chargé après celui du
  noyau et l'emporte.
- `defaultTheme` s'applique aux utilisateurs qui n'ont pas encore choisi de
  thème ; un choix enregistré dans le navigateur est conservé.

## Ce que vous pouvez importer sans risque

Ces modules restent rétrocompatibles, et les changements incompatibles sont
signalés dans les notes de version :

- Backend : `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`, `services.audit`
- Frontend : `@/extensions`, `@/shared/*`, `@/components/ui/*`

Tout le reste (services, parties internes des pages du noyau) peut changer d'une
version à l'autre.

## Limites

Ceci nécessite encore de modifier les fichiers du noyau :

- L'en-tête, le layout général, la page de connexion et les autres pages hors du
  layout des utilisateurs connectés
- Masquer un lien du noyau dans la barre latérale (on peut le remplacer, pas le
  supprimer)
- Ajouter un élément à une page du noyau (une colonne, un bouton) sans remplacer
  la page
- Le prompt système de l'assistant de chat et le traitement des documents (les
  endpoints peuvent être remplacés, pas les étapes internes)
