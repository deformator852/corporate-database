"""Loads extension packages: customizations from custom/<name>/.

Upstream never ships files under custom/, so pulling updates does not conflict
with them (see documentations/customization/). Core code never imports from
it.

A package may define any of:
    CORE_API     the extension API version it was written for; a package
                 written for another one is skipped with an error in the log.
    router       APIRouter mounted under /api/v1 before core routers, so the
                 same method + path replaces a core endpoint.
    PERMISSIONS  tuple of (key, name, description), seeded with the core ones.
    setup(app)   called with the FastAPI app (dependency_overrides, middleware).
Importing the package registers its SQLAlchemy models with Alembic.
custom/<name>/tasks.py, if present, is loaded by the Celery worker, and
custom/migrations/ holds the Alembic migrations of custom packages.
"""

import importlib
import logging
import pkgutil
from functools import cache
from pathlib import Path
from types import ModuleType

# Raised when the extension points change incompatibly.
CORE_API = 2

SRC_DIR = Path(__file__).resolve().parent
CUSTOM_DIR = SRC_DIR / "custom"

logger = logging.getLogger(__name__)


def _packages() -> list[str]:
    return sorted(
        f"{CUSTOM_DIR.name}.{info.name}"
        for info in pkgutil.iter_modules([str(CUSTOM_DIR)])
        if info.ispkg and not info.name.startswith("_") and info.name != "migrations"
    )


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
