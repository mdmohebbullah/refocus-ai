"""Connected Google Docs / Word documents — read-only."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..config import get_settings
from ..db import get_db
from ..deps import account_user, current_user, owned, owned_project
from ..integrations import external_docs as X
from ..integrations.docx_reader import paragraphs_from_docx
from ..models import ConnectedAccount, Document, User
from ..schemas import ExternalDocIn

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("/accounts")
def accounts(user: User = Depends(account_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id)).all()
    return {"accounts": [{"provider": a.provider, "account_email": a.account_email, "scopes": a.scopes, "connected_at": S.iso(a.created_at)} for a in rows],
            "configured": {"google": X.configured("google"), "microsoft": X.configured("microsoft")},
            "access": "Read-only. Re-Focus AI can open and read connected documents but never edits them."}


@router.get("/{provider}/start")
def oauth_start(provider: str, user: User = Depends(account_user), db: Session = Depends(get_db)):
    if provider not in ("google", "microsoft"):
        raise HTTPException(404)
    return {"url": X.start_url(db, user, provider)}


@router.get("/{provider}/callback")
def oauth_callback(provider: str, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    front = get_settings().frontend_url
    if error or not code:
        return RedirectResponse(f"{front}/settings?connect_error={error or 'cancelled'}")
    try:
        X.finish(db, provider, code, state)
    except HTTPException as e:
        return RedirectResponse(f"{front}/settings?connect_error={e.detail}")
    return RedirectResponse(f"{front}/settings?connected={provider}")


@router.delete("/{provider}", status_code=204)
def disconnect(provider: str, user: User = Depends(account_user), db: Session = Depends(get_db)):
    """Deletes the stored (encrypted) tokens. Connected documents stay, as read-only snapshots."""
    acct = db.scalar(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id, ConnectedAccount.provider == provider))
    if acct:
        db.delete(acct)
        db.commit()


@router.post("/documents", status_code=201)
def connect_document(body: ExternalDocIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, body.project_id, user.id)
    if body.provider == "google":
        doc_id = X.google_doc_id(body.url_or_id)
        title, paras = X.fetch_google(db, user.id, doc_id)
        d = Document(user_id=user.id, project_id=body.project_id, title=body.title or title, source="google_docs", external_id=doc_id,
                     external_url=f"https://docs.google.com/document/d/{doc_id}/edit")
    else:
        title, paras, item_path, web_url = X.fetch_word(db, user.id, body.url_or_id.strip())
        d = Document(user_id=user.id, project_id=body.project_id, title=body.title or title, source="word", external_id=item_path, external_url=web_url)
    db.add(d)
    db.flush()
    X.store_snapshot(db, user, d, None, paras)
    db.commit()
    return S.document(d)


@router.post("/word/upload", status_code=201)
async def upload_docx(file: UploadFile = File(...), project_id: int = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large (25 MB max)")
    try:
        paras = paragraphs_from_docx(data)
    except Exception:
        raise HTTPException(422, "That file couldn't be read as a Word .docx document.")
    d = Document(user_id=user.id, project_id=project_id, title=(file.filename or "Word document").removesuffix(".docx"), source="word")
    db.add(d)
    db.flush()
    X.store_snapshot(db, user, d, None, paras)
    db.commit()
    return S.document(d)


@router.post("/documents/{doc_id}/upload")
async def reupload_docx(doc_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Give Re-Focus AI a newer copy of an uploaded Word file (the original on your computer is untouched)."""
    d = owned(db, Document, doc_id, user.id)
    if d.source != "word" or d.external_id:
        raise HTTPException(409, "Only uploaded Word documents can be refreshed by upload")
    X.store_snapshot(db, user, d, None, paragraphs_from_docx(await file.read()))
    db.commit()
    return S.document(d)


@router.post("/documents/{doc_id}/refresh")
def refresh(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db, Document, doc_id, user.id)
    if d.source == "builtin":
        raise HTTPException(409, "Built-in documents are edited directly")
    if d.source == "word" and not d.external_id:
        raise HTTPException(409, "Upload a newer copy of this Word file to refresh it")
    snap = X.store_snapshot(db, user, d)
    db.commit()
    return {"document": S.document(d), "paragraphs": len(snap.paragraphs)}
