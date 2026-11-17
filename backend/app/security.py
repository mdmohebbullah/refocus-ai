import base64
import hashlib
import json
import secrets
from datetime import timedelta

import jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

from .config import get_settings
from .models import utcnow

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    s = get_settings()
    payload = {"sub": str(user_id), "exp": utcnow() + timedelta(minutes=s.access_token_minutes), "typ": "access"}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        if data.get("typ") != "access":
            return None
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_device_token() -> str:
    return "rfd_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet() -> Fernet:
    s = get_settings()
    key = s.token_encryption_key
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(("enc:" + s.secret_key).encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()).decode())
