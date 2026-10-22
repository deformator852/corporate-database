# Personnaliser Corpus

Ce guide montre comment ajouter des pages, des endpoints d'API, des
autorisations, des thèmes et des traductions à Corpus sans modifier les
fichiers du noyau, pour que les mises à jour se fusionnent sans conflit.

Autres langues : [English](en.md) · [Español](es.md)

## À propos des extensions

Vos modifications vivent dans deux dossiers. Les mises à jour n'y ajoutent
jamais de fichiers, donc une nouvelle version se fusionne sans conflit.

| Dossier | Contenu |
|---|---|
| `backend/src/custom/EXTENSION/` | Paquets Python : endpoints d'API, modèles, autorisations, tâches en arrière-plan |
| `backend/src/custom/migrations/` | Vos migrations Alembic |
| `frontend/src/custom/EXTENSION/index.ts(x)` | Pages, liens de la barre latérale, traductions, thèmes |

Remplacez EXTENSION par un nom de dossier de votre choix, par exemple `crm` ou
`hr`. Vous pouvez avoir plusieurs extensions. Elles sont chargées par ordre
alphabétique, et les dossiers dont le nom commence par `_` sont ignorés. Vous
n'avez rien à déclarer : Corpus trouve les deux dossiers automatiquement.

Vous pouvez toujours modifier les fichiers du noyau, mais chaque modification
peut provoquer un conflit à la prochaine mise à jour. Utilisez d'abord une
extension, et ne modifiez le noyau que s'il n'existe pas de point d'extension
pour votre besoin. Voir [Limites](#limites).

## Ce que vous pouvez importer

Ces modules restent rétrocompatibles, et leurs changements incompatibles sont
indiqués dans les notes de version :

* Backend : `database`, `models`, `api.deps`, `exceptions`, `settings`,
  `extensions`, `worker`, `services.audit`
* Frontend : `@/extensions`, `@/shared/*`, `@/components/ui/*`

Tout le reste, comme les services ou les parties internes des pages du noyau,
peut changer d'une version à l'autre.

## Points d'extension du backend

Un paquet `backend/src/custom/EXTENSION/__init__.py` peut définir l'un des
éléments suivants :

| Nom | Rôle |
|---|---|
| `router` | Un `APIRouter` monté sous `/api/v1` **avant** les routeurs du noyau |
| `PERMISSIONS` | `((key, name, description), ...)`, initialisées avec les autorisations du noyau |
| `setup(app)` | Une fonction appelée une fois avec l'application FastAPI au démarrage |
| Modèles | Alembic voit tout modèle SQLAlchemy importé par le paquet |
| `tasks.py` | Un module chargé par le worker Celery, s'il existe |
| `CORE_API` | La version de l'API d'extensions pour laquelle le paquet a été écrit, actuellement `1`. Un paquet écrit pour une autre version est ignoré, avec une erreur dans le journal |

## Ajouter des endpoints d'API

1. Écrivez le routeur :

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

2. Exportez-le depuis le paquet :

   ```python
   # backend/src/custom/crm/__init__.py
   from .api import router
   ```

L'endpoint est servi à `/api/v1/crm/hello`. Suivez les règles du projet pour
l'authentification et les erreurs : utilisez `Depends(get_current_user)` ou
`require_permission(...)`, et levez `AppError(code, message, status_code)` de
`exceptions`.

## Remplacer un endpoint du noyau

Les routeurs personnalisés sont montés en premier, donc une route avec la même
méthode et le même chemin l'emporte. Ceci remplace `GET /api/v1/users` :

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(...):
    ...
```

Conservez la forme de réponse attendue par le frontend du noyau, ou remplacez
aussi la page.

## Ajouter des autorisations

1. Déclarez les autorisations. Utilisez des clés `ressource.action` qui
   n'entrent pas en conflit avec les ressources du noyau.

   ```python
   # backend/src/custom/crm/__init__.py
   PERMISSIONS = (
       ("crm.report", "Rapport CRM", "Voir le rapport CRM"),
   )
   ```

2. Initialisez-les :

   ```sh
   cd backend/src && uv run python -m seeders.run
   ```

Les autorisations apparaissent alors sur la page **Autorisations** et peuvent
être attribuées à des rôles. Le rôle Admin les reçoit automatiquement.

## Exécuter du code au démarrage

`setup(app)` peut ajouter des middlewares et des gestionnaires d'exceptions,
ou remplacer toute dépendance que le noyau injecte avec `Depends(...)` :

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

Une entrée dans `app.dependency_overrides` remplace cette dépendance partout à
la fois.

## Stocker vos propres données

N'ajoutez pas de colonnes aux tables du noyau comme `users`. Mettez vos données
dans votre propre table avec une clé un-à-un, pour que le noyau puisse
modifier ses tables librement.

1. Définissez le modèle. Préfixez le nom de la table par `custom_` pour éviter
   les conflits avec les futures tables du noyau.

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
       user: Mapped[User] = relationship(backref="profile")  # user.profile fonctionne aussi
   ```

2. Importez le module dans le paquet pour qu'Alembic voie la table :

   ```python
   # backend/src/custom/crm/__init__.py
   from . import models  # noqa: F401
   from .api import router
   ```

3. Créez une migration. Voir [Créer des migrations](#créer-des-migrations).

Les tables non liées aux utilisateurs fonctionnent de la même façon.

## Créer des migrations

Les migrations personnalisées sont sur leur propre branche Alembic, `custom`,
donc les migrations du noyau n'entrent jamais en conflit avec elles.

1. Mettez la base de données à jour :

   ```sh
   cd backend
   uv run alembic upgrade heads
   mkdir -p src/custom/migrations
   ```

2. Générez la migration. Pour la première migration personnalisée uniquement,
   démarrez la branche `custom` après le head du noyau :

   ```sh
   uv run alembic revision --autogenerate -m "crm profiles" \
     --head base --branch-label custom --version-path src/custom/migrations \
     --depends-on $(uv run alembic heads | awk '{print $1; exit}')
   ```

   Pour chaque migration suivante :

   ```sh
   uv run alembic revision --autogenerate -m "MESSAGE" --head custom@head
   ```

3. Vérifiez le fichier généré, puis appliquez-le :

   ```sh
   uv run alembic upgrade heads
   ```

Utilisez toujours `upgrade heads`, au pluriel : la commande applique la branche
du noyau et la branche personnalisée.

## Ajouter des tâches en arrière-plan

Écrivez une tâche Celery dans `tasks.py` de votre paquet. Préfixez son `name`
par le nom de votre extension pour éviter les collisions.

```python
# backend/src/custom/crm/tasks.py
from worker import celery


@celery.task(name="crm.sync")
def sync() -> None:
    ...
```

Lancez-la depuis votre endpoint avec `sync.delay()`.

## Enregistrer des entrées d'audit

Enregistrez vos propres actions avec `AuditService` de
`Depends(get_audit_service)` dans `api.deps` :

```python
audit.record("crm.export", actor=user, target_label=...)
```

Les entrées apparaissent sur la page **Journal d’audit** sous le nom de leur
action. N'enregistrez jamais de mots de passe, de jetons ni d'autres secrets.

## Points d'extension du frontend

Un fichier `frontend/src/custom/EXTENSION/index.tsx` exporte par défaut une
`Extension`. Le type est dans `frontend/src/extensions.ts`.

| Champ | Rôle |
|---|---|
| `routes` | Pages dans la mise en page connectée, avec l'en-tête et la barre latérale |
| `nav` | Liens de la barre latérale, après ceux du noyau |
| `messages` | Traductions par langue |
| `themes` | Thèmes supplémentaires dans le sélecteur de thème |
| `defaultTheme` | Le thème des utilisateurs qui n'en ont pas choisi |
| `coreApi` | La version de l'API d'extensions pour laquelle le module a été écrit, actuellement `1`. Un module écrit pour une autre version est ignoré, avec une erreur dans la console du navigateur |

## Ajouter une page

1. Écrivez la page :

   ```tsx
   // frontend/src/custom/crm/Report.tsx
   import {useI18n} from "@/shared/i18n/I18nProvider";

   export function Report() {
       const {t} = useI18n();
       return <h1>{t("custom.crm.title")}</h1>;
   }
   ```

2. Enregistrez-la avec un lien dans la barre latérale et ses traductions :

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

`can` masque le lien aux utilisateurs sans cette autorisation. Pour bloquer aussi
la page, ajoutez `handle: {can: "crm.report"}` à la route : les utilisateurs
sans l'autorisation voient la page introuvable. Dans une page,
utilisez `can("crm.report")` de `@/shared/lib/api/me`. Appelez votre backend
avec le client partagé `api` : son URL de base est `/api/v1`, et il envoie les
cookies de session.

## Remplacer une page du noyau

Une route avec le même `path` remplace la page du noyau, et `index: true`
remplace l'Accueil. Les chemins du noyau sont `index` (Accueil), `documents`,
`users`, `users/:userId`, `roles`, `permissions`, `feedback`, `chat-history`,
`chat-history/:conversationId`, `account`, `audit`, `system` et `errors`.

```tsx
routes: [{path: "users", Component: MyUsersPage}],
```

Le plus simple est de copier la page du noyau dans `custom/`, de modifier la
copie et de l'enregistrer sous le même chemin. Votre copie ne reçoit pas les
corrections du noyau pour cette page, comparez-la donc avec le noyau après
chaque mise à jour.

## Modifier les liens de la barre latérale

Les éléments de `nav` sont ajoutés après ceux du noyau. Un élément avec le même
`to` remplace le lien du noyau, par exemple pour le renommer ou exiger une
autre autorisation :

```tsx
nav: [{to: "/documents", labelKey: "custom.nav.files", end: true, can: "documents.list"}],
```

## Ajouter des traductions

* Les nouvelles clés doivent commencer par `custom.`, par exemple
  `custom.crm.title`.
* Vous pouvez remplacer des clés du noyau, par exemple
  `"nav.documents": "Fichiers"`.
* Les langues sont `en`, `es` et `fr`. Une clé manquante utilise `en`, puis la
  clé elle-même.
* L'interface utilise les langues choisies dans `uv run install` ou
  `uv run configure` (`APP_LANGUAGE`, la langue par défaut, et
  `APP_LANGUAGES`, entre lesquelles les utilisateurs basculent dans l'en-tête,
  dans `backend/.env`). Donnez une valeur à vos clés dans chacune d'elles.

## Ajouter des thèmes

Un thème est un ensemble de variables CSS sous `[data-theme="THEME-ID"]` plus
une entrée dans `themes`. Gardez les deux dans votre dossier `custom/`.

1. Écrivez le CSS. Remplacez THEME-ID par l'identifiant de votre thème, ici
   `ocean` :

   ```css
   /* frontend/src/custom/brand/ocean.css */
   [data-theme="ocean"] {
     --background: #ecfeff;
     --foreground: #083344;
     --primary: #0e7490;
     --primary-foreground: #ffffff;
     --ring: #0e7490;
     /* toute variable de :root dans frontend/src/index.css */
   }

   [data-theme="ocean"] .app-header {
     background-color: var(--primary);
     color: var(--primary-foreground);
   }
   ```

2. Enregistrez le thème et importez le CSS :

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
           fr: {"custom.theme.ocean": "Océan", "custom.theme.graphite": "Graphite"},
       },
   } satisfies Extension;
   ```

Options du thème :

* `id` est la valeur de `data-theme` sur `<html>`. Stylez-le uniquement dans
  votre fichier CSS, importé depuis le module de l'extension.
* La liste complète des variables (`--background`, `--primary`, `--sidebar`,
  `--success` et d'autres) se trouve dans `:root` de
  `frontend/src/index.css`. Les variables que vous ne définissez pas gardent
  les valeurs du noyau.
* `dark: true` ajoute la classe `.dark` et un schéma de couleurs sombre pour
  les contrôles du navigateur.
* Un thème avec le même `id` qu'un thème du noyau (`neutral`, `ledger`,
  `slate`, `midnight`, `vault`) remplace son libellé et ses options. Votre CSS
  se charge après celui du noyau et l'emporte.
* `defaultTheme` s'applique aux utilisateurs qui n'ont pas encore choisi de
  thème. Un choix enregistré dans le navigateur est conservé.

## Obtenir les mises à jour

1. Ajoutez une fois le dépôt principal. Remplacez UPSTREAM-URL par son
   adresse.

   ```sh
   git remote add upstream UPSTREAM-URL
   ```

2. Récupérez la mise à jour, appliquez les migrations du noyau et de vos
   extensions, et initialisez les nouvelles autorisations :

   ```sh
   git pull upstream main
   cd backend && uv run alembic upgrade heads
   cd src && uv run python -m seeders.run
   ```

3. Redémarrez le backend, le worker Celery et le serveur de développement du
   frontend.

## Limites

Ces modifications demandent encore de toucher aux fichiers du noyau :

* L'en-tête, la mise en page générale, la page de connexion et les autres
  pages hors de la mise en page connectée
* Masquer un lien du noyau dans la barre latérale. Vous pouvez le remplacer,
  mais pas le supprimer.
* Ajouter un élément à une page du noyau, comme une colonne ou un bouton, sans
  remplacer toute la page
* Le prompt système de l'assistant et la chaîne de traitement des documents.
  Vous pouvez remplacer des endpoints, mais pas leurs étapes internes.
