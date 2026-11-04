import bcrypt

from models.rbac.constants import ADMIN_ROLE_KEY
from models.user import User
from settings import oidc_config

# bcrypt only reads the first 72 bytes and bcrypt>=5 raises beyond that.
# About 36 Cyrillic characters; enforced on create/update in schemas.
MAX_PASSWORD_BYTES = 72


def password_fits(plain: str) -> bool:
    return len(plain.encode()) <= MAX_PASSWORD_BYTES


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    # No stored password can be longer, so a longer input is simply wrong.
    if not password_fits(plain):
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def uses_password(user: User) -> bool:
    """Signs in with an Archfold password: always without single sign-on; with
    it, administrators only (their way in when the provider is down). The
    user's roles must be loaded."""
    if user.password is None:
        return False
    return oidc_config() is None or any(role.key == ADMIN_ROLE_KEY for role in user.roles)
