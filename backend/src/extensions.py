"""Loads project customizations from custom/<name>/ packages.

Upstream never ships files under custom/, so pulling updates does not conflict
with them. See documentations/customization/.

A package in custom/ may define any of:
    router       APIRouter mounted under /api/v1 before core routers, so the
                 same method + path replaces a core endpoint.
    PERMISSIONS  tuple of (key, name, description), seeded with the core ones.
    setup(app)   called with the FastAPI app (dependency_overrides, middleware).
Importing the package registers its SQLAlchemy models with Alembic.
custom/<name>/tasks.py, if present, is loaded by the Celery worker.
"""

import importlib
import pkgutil
from functools import cache
from pathlib import Path
from types import ModuleType

CUSTOM_DIR = Path(__file__).resolve().parent / "custom"


def _names() -> list[str]:
    return sorted(
        info.name
        for info in pkgutil.iter_modules([str(CUSTOM_DIR)])
        if info.ispkg and not info.name.startswith("_")
    )


@cache
def plugins() -> tuple[ModuleType, ...]:
    return tuple(importlib.import_module(f"custom.{name}") for name in _names())


def task_modules() -> list[str]:
    return [
        f"custom.{name}.tasks"
        for name in _names()
        if (CUSTOM_DIR / name / "tasks.py").exists()
    ]
