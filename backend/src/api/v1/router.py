from fastapi import APIRouter

from extensions import plugins

from . import audit, auth, chat, documents, notifications, permissions, roles, system, users

api_router = APIRouter(prefix="/api/v1")

# First, so a custom route with the same method + path wins over core.
for plugin in plugins():
    if hasattr(plugin, "router"):
        api_router.include_router(plugin.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(permissions.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(notifications.router)
api_router.include_router(audit.router)
api_router.include_router(system.router)
