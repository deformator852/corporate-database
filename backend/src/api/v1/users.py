from fastapi import APIRouter, Depends

from api.deps import require_permission
from models import User

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.get("/")
async def get_users(
    user: User = Depends(require_permission("users.list")),
):
    return user
