from fastapi import APIRouter

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.get("/")
async def list_users():
    ...


@router.get("/{user_id}")
async def get_user(user_id: int):
    ...


@router.post("/")
async def create_user():
    ...