from fastapi import APIRouter

from . import auth, chat, documents, notifications, permissions, roles, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(permissions.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(notifications.router)
