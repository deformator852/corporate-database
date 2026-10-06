"""Loads extension packages: customizations from custom/<name>/ and the
paid features from advanced/<name>/.

Upstream never ships files under custom/, so pulling updates does not conflict
with them (see documentations/customization/). advanced/ is not in the core
repository: the advanced edition puts its packages there when it is installed.
Without it the core runs as is. Core code never imports from either folder.

A package may define any of:
    CORE_API     the extension API version it was written for; a package
                 written for another one is skipped with an error in the log.
    router       APIRouter mounted under /api/v1 before core routers, so the
                 same method + path replaces a core endpoint.
    PERMISSIONS  tuple of (key, name, description), seeded with the core ones.
    setup(app)   called with the FastAPI app (dependency_overrides, middleware).
Importing the package registers its SQLAlchemy models with Alembic.
<folder>/<name>/tasks.py, if present, is loaded by the Celery worker, and
<folder>/migrations/ holds the folder's Alembic migrations.

custom/ packages come first: a customer's router is mounted before an
advanced one and so replaces it too.
"""

import importlib
import logging
import pkgutil
from functools import cache
from pathlib import Path
from types import ModuleType

# Raised when the extension points change incompatibly.
CORE_API = 1

SRC_DIR = Path(__file__).resolve().parent
CUSTOM_DIR = SRC_DIR / "custom"
ADVANCED_DIR = SRC_DIR / "advanced"
_FOLDERS = (CUSTOM_DIR, ADVANCED_DIR)

logger = logging.getLogger(__name__)


def _names(folder: Path) -> list[str]:
    return sorted(
        info.name
        for info in pkgutil.iter_modules([str(folder)])
        if info.ispkg and not info.name.startswith("_") and info.name != "migrations"
    )


def _packages() -> list[str]:
    return [f"{folder.name}.{name}" for folder in _FOLDERS for name in _names(folder)]


@cache
def plugins() -> tuple[ModuleType, ...]:
    loaded: list[ModuleType] = []
    for name in _packages():
        module = importlib.import_module(name)
        wanted = getattr(module, "CORE_API", CORE_API)
        if wanted != CORE_API:
            logger.error("Extension %s needs extension API %s, this core has %s; skipped", name, wanted, CORE_API)
            continue
        loaded.append(module)
    return tuple(loaded)


def task_modules() -> list[str]:
    return [
        f"{plugin.__name__}.tasks"
        for plugin in plugins()
        if SRC_DIR.joinpath(*plugin.__name__.split("."), "tasks.py").exists()
    ]
