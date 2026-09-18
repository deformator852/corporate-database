from sqlalchemy.ext.asyncio import AsyncSession


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
