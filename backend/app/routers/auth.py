from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, current_user, ensure_settings, get_principal
from ..models import User
from ..schemas import LoginIn, PreferencesPatch, RegisterIn
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])

DEFAULT_SHORTCUTS = {
    "pause_session": "Alt+Shift+P",
    "resume_session": "Alt+Shift+R",
    "save_thought": "Alt+Shift+T",
    "save_checkpoint": "Alt+Shift+S",
    "panel_back": "Alt+Shift+ArrowLeft",
    "panel_forward": "Alt+Shift+ArrowRight",
    "older_checkpoint": "Alt+Shift+[",
    "newer_checkpoint": "Alt+Shift+]",
    "search": "Alt+Shift+K",
}
RESERVED = {"Alt+ArrowLeft", "Alt+ArrowRight", "Ctrl+[", "Ctrl+]", "Meta+[", "Meta+]", "Ctrl+T", "Ctrl+W", "Ctrl+L",
            "Ctrl+R", "Ctrl+N", "Ctrl+Tab", "Meta+T", "Meta+W", "Meta+L", "Meta+R", "Ctrl+K", "Meta+K", "F5"}


def me_payload(db: Session, user: User) -> dict:
    prefs, priv = ensure_settings(db, user)
    return {"id": user.id, "email": user.email, "name": user.name,
            "preferences": {"help_level": prefs.help_level, "theme": prefs.theme, "current_project_id": prefs.current_project_id,
                            "break_threshold_minutes": prefs.break_threshold_minutes, "break_reminders": prefs.break_reminders,
                            "inactivity_gap_minutes": prefs.inactivity_gap_minutes,
                            "shortcuts": {**DEFAULT_SHORTCUTS, **(prefs.shortcuts or {})},
                            "voice_upload_allowed": prefs.voice_upload_allowed},
            "privacy": {"private_mode": priv.private_mode, "activity_collection": priv.activity_collection}}


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    ensure_settings(db, user)
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": me_payload(db, user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": me_payload(db, user)}


@router.get("/me")
def me(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    out = me_payload(db, p.user)
    out["device"] = {"id": p.device.id, "name": p.device.name, "collection_enabled": p.device.collection_enabled,
                     "content_access": p.device.content_access} if p.device else None
    return out


@router.patch("/me/preferences")
def update_preferences(body: PreferencesPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prefs, _ = ensure_settings(db, user)
    data = body.model_dump(exclude_unset=True)
    if data.pop("clear_help_level", False):
        prefs.help_level = None
    if "shortcuts" in data and data["shortcuts"] is not None:
        merged = {**DEFAULT_SHORTCUTS, **(prefs.shortcuts or {}), **data.pop("shortcuts")}
        clashes = [k for k, v in merged.items() if v in RESERVED]
        if clashes:
            raise HTTPException(422, f"These shortcuts clash with browser controls: {', '.join(clashes)}")
        values = [v for v in merged.values() if v]
        if len(values) != len(set(values)):
            raise HTTPException(422, "Two actions cannot share the same shortcut")
        prefs.shortcuts = {k: v for k, v in merged.items() if DEFAULT_SHORTCUTS.get(k) != v}
    for k, v in data.items():
        if v is not None or k == "current_project_id":
            setattr(prefs, k, v)
    db.commit()
    return me_payload(db, user)
