"""密码哈希 + Session 签名。"""
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_signer = TimestampSigner(settings.SESSION_SECRET)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def create_session_token(username: str) -> str:
    return _signer.sign(username.encode("utf-8")).decode("utf-8")


def verify_session_token(token: str) -> str | None:
    """成功返回 username，失败返回 None。"""
    try:
        raw = _signer.unsign(token, max_age=settings.SESSION_MAX_AGE)
        return raw.decode("utf-8")
    except (BadSignature, SignatureExpired):
        return None
