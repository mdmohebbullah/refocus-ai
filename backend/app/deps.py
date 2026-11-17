from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import (DeviceConnection, PrivacySettings, Project, User, UserPreferences, utcnow)
from .security import decode_access_token, hash_token

bearer = HTTPBearer(auto_error=False)


class Principal:
    """The authenticated caller: a signed-in user, optionally through a paired device."""

    def __init__(self, user: User, device: DeviceConnection | None = None):
        self.user = user
        self.device = device

    @property
    def id(self) -> int:
        return self.user.id


def get_principal(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    token = creds.credentials
    if token.startswith("rfd_"):
        device = db.scalar(select(DeviceConnection).where(DeviceConnection.token_hash == hash_token(token)))
        if not device:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or revoked device")
        device.last_seen_at = utcnow()
        db.commit()
        user = db.get(User, device.user_id)
        return Principal(user, device)
    uid = decode_access_token(token)
    user = db.get(User, uid) if uid else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return Principal(user)


def current_user(p: Principal = Depends(get_principal)) -> User:
    return p.user


def account_user(p: Principal = Depends(get_principal)) -> User:
    """For account-level actions (export, deletion, pairing, connected accounts, clearing history).
    A browser-extension device token can't do these — only a signed-in person can."""
    if p.device is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action needs you to sign in to Re-Focus AI; a device token can't do it")
    return p.user


def ensure_settings(db: Session, user: User) -> tuple[UserPreferences, PrivacySettings]:
    prefs = db.get(UserPreferences, user.id)
    priv = db.get(PrivacySettings, user.id)
    changed = False
    if not prefs:
        prefs = UserPreferences(user_id=user.id, shortcuts={})
        db.add(prefs)
        changed = True
    if not priv:
        priv = PrivacySettings(user_id=user.id, excluded_domains=[], removed_default_exclusions=[], approved_domains=[])
        db.add(priv)
        changed = True
    if changed:
        db.commit()
    return prefs, priv


def owned(db: Session, model, obj_id: int, user_id: int):
    """Fetch a row owned by the user or raise 404 (never reveal other users' data)."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def owned_project(db: Session, project_id: int, user_id: int) -> Project:
    return owned(db, Project, project_id, user_id)
