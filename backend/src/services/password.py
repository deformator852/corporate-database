import bcrypt

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
