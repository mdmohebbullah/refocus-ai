"""Privacy, export, deletion (Feature 23) and voice transcription (Feature 18)."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..config import get_settings
from ..db import get_db
from ..deps import Principal, account_user, current_user, ensure_settings, get_principal
from ..models import (ActivityEvent, AISuggestion, BrowserTab, Checkpoint, ConnectedAccount, DeviceConnection, Document,
                      DocumentVersion, ExternalDocumentSnapshot, FutureSelfQuestion, PinnedItem, Project, Reference, SourceSelection,
                      SuggestionFeedback, Task, TimeTrackingRecord, UnfinishedThought, User, UserNote, WorkSession, utcnow)
from ..privacy import DEFAULT_SENSITIVE_DOMAINS, domain_of, effective_exclusions
from ..schemas import PrivacyPatch
from ..security import verify_password
from .browser import purge_expired

router = APIRouter(prefix="/api", tags=["privacy"])

DELETION_NOTES = [
    "Deleting removes the data from Re-Focus AI's database immediately.",
    "Copies you already exported, downloaded, or copied elsewhere are not affected.",
    "Text that was already sent to the AI provider for a suggestion may be kept by that provider under its own retention policy "
    "(OpenAI API data is not used for training by default). Placeholder AI mode sends nothing outside Re-Focus AI.",
    "Database backups, if your deployment keeps them, expire on the backup schedule.",
    "Google Docs and Word files are never changed or deleted — Re-Focus AI only removes its own read-only snapshots.",
]


def privacy_payload(db: Session, user: User) -> dict:
    _, priv = ensure_settings(db, user)
    return {"private_mode": priv.private_mode, "activity_collection": priv.activity_collection,
            "excluded_domains": priv.excluded_domains or [], "removed_default_exclusions": priv.removed_default_exclusions or [],
            "effective_exclusions": effective_exclusions(priv), "default_categories": DEFAULT_SENSITIVE_DOMAINS,
            "always_excluded": ["Any page with a password field", "Checkout, payment, billing and sign-in pages", "Browser-internal pages (chrome://, file://)"],
            "remember_tab_preferences": priv.remember_tab_preferences, "approved_domains": priv.approved_domains or [],
            "history_retention_days": priv.history_retention_days, "deletion_notes": DELETION_NOTES,
            "ai_provider": "openai" if get_settings().ai_enabled else "placeholder"}


@router.get("/privacy")
def get_privacy(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return privacy_payload(db, user)


def _norm_domain(d: str) -> str:
    d = (d or "").strip().lower()
    if "://" in d:
        d = domain_of(d) or ""
    return d.split("/")[0].split(":")[0].removeprefix("www.")


@router.patch("/privacy")
def update_privacy(body: PrivacyPatch, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    user = p.user
    _, priv = ensure_settings(db, user)
    data = body.model_dump(exclude_unset=True)
    if p.device is not None and set(data) - {"private_mode"}:
        # The extension popup may only switch private mode; everything else is changed in the web app.
        raise HTTPException(403, "Change privacy settings in the Re-Focus AI web app")
    for k in ("excluded_domains", "approved_domains", "removed_default_exclusions"):
        if data.get(k) is not None:
            data[k] = sorted({d for d in (_norm_domain(x) for x in data[k]) if d})
    for k, v in data.items():
        if v is not None:
            setattr(priv, k, v)
    if priv.private_mode or not priv.activity_collection:
        # Stop using live tab data immediately.
        for t in db.scalars(select(BrowserTab).where(BrowserTab.user_id == user.id)):
            db.delete(t)
    purge_expired(db, user.id, priv)
    db.commit()
    return privacy_payload(db, user)


@router.get("/privacy/export")
def export_data(user: User = Depends(account_user), db: Session = Depends(get_db)):
    """Everything Re-Focus AI stores about you, as JSON. OAuth tokens are never exported."""
    prefs, priv = ensure_settings(db, user)

    def rows(model, ser=None):
        items = db.scalars(select(model).where(model.user_id == user.id)).all()
        if ser:
            return [ser(i) for i in items]
        def val(v):
            return S.iso(v) if isinstance(v, datetime) else v
        return [{c.name: val(getattr(i, c.name)) for c in model.__table__.columns
                 if c.name not in ("token_hash", "token_encrypted", "password_hash")} for i in items]
    return {
        "exported_at": utcnow().isoformat(), "format": "re-focus-ai-export/v1",
        "account": {"email": user.email, "name": user.name, "created_at": S.iso(user.created_at)},
        "preferences": {"help_level": prefs.help_level, "theme": prefs.theme, "shortcuts": prefs.shortcuts,
                        "break_threshold_minutes": prefs.break_threshold_minutes, "break_reminders": prefs.break_reminders},
        "privacy": privacy_payload(db, user),
        "projects": rows(Project), "documents": rows(Document), "document_versions": rows(DocumentVersion),
        "external_document_snapshots": rows(ExternalDocumentSnapshot), "checkpoints": rows(Checkpoint),
        "source_selections": rows(SourceSelection), "unfinished_thoughts": rows(UnfinishedThought),
        "future_self_questions": rows(FutureSelfQuestion), "notes": rows(UserNote), "references": rows(Reference),
        "tasks": rows(Task), "pins": rows(PinnedItem), "ai_suggestions": rows(AISuggestion), "suggestion_feedback": rows(SuggestionFeedback),
        "work_sessions": rows(WorkSession), "time_records": rows(TimeTrackingRecord), "activity_events": rows(ActivityEvent),
        "devices": rows(DeviceConnection), "connected_accounts": [{"provider": a.provider, "account_email": a.account_email, "scopes": a.scopes}
                                                                  for a in db.scalars(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id))],
    }


@router.post("/account/delete")
def delete_account(body: dict, user: User = Depends(account_user), db: Session = Depends(get_db)):
    if not verify_password(body.get("password", ""), user.password_hash):
        raise HTTPException(403, "Password is incorrect")
    if body.get("confirm") != "DELETE":
        raise HTTPException(422, "Type DELETE to confirm")
    db.delete(user)  # cascades to every table owned by the user
    db.commit()
    return {"deleted": True, "notes": DELETION_NOTES}


# ------------------------------------------------------------------ voice (Feature 18)
@router.post("/voice/transcribe")
async def transcribe(audio: UploadFile = File(...), project_id: int | None = Form(None), user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    """Only used when the user allowed audio upload. The audio is transcribed and discarded, never stored."""
    prefs, _ = ensure_settings(db, user)
    if not prefs.voice_upload_allowed:
        raise HTTPException(403, "Audio upload is turned off. Turn it on in Settings, or type your thought.")
    s = get_settings()
    if not s.ai_enabled:
        raise HTTPException(503, "Server transcription is not configured (no OPENAI_API_KEY). Please type your thought.")
    data = await audio.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Recording too long")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=s.openai_api_key)
        r = client.audio.transcriptions.create(model=s.openai_transcribe_model, file=(audio.filename or "thought.webm", data))
        return {"text": r.text, "provider": "openai"}
    except Exception as e:  # pragma: no cover - network
        raise HTTPException(502, f"Transcription failed: {e}. Please type your thought.")
