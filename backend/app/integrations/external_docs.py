"""Read-only Google Docs / Microsoft Word integration.

Re-Focus AI only ever READS these documents:
* Google: Docs API `documents.get` with the `documents.readonly` scope.
* Microsoft: Graph `GET …/driveItem` and `GET …/content` with `Files.Read.All`.
The only POST requests go to the OAuth token endpoints. No request ever writes to a document.
"""
from __future__ import annotations

import base64
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ConnectedAccount, Document, ExternalDocumentSnapshot, OAuthState, User, aware, utcnow
from ..security import decrypt_json, encrypt_json
from . import http
from .docx_reader import paragraphs_from_docx

GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/documents.readonly https://www.googleapis.com/auth/drive.metadata.readonly"
MS_SCOPES = "offline_access openid email User.Read Files.Read.All"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
DOCS_API = "https://docs.googleapis.com/v1/documents/"
GRAPH = "https://graph.microsoft.com/v1.0"


def _ms(path: str) -> str:
    return f"https://login.microsoftonline.com/{get_settings().microsoft_tenant}/oauth2/v2.0/{path}"


def redirect_uri(provider: str) -> str:
    return f"{get_settings().public_api_url}/api/integrations/{provider}/callback"


def configured(provider: str) -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret) if provider == "google" else bool(s.microsoft_client_id and s.microsoft_client_secret)


# ------------------------------------------------------------------ OAuth
def start_url(db: Session, user: User, provider: str) -> str:
    if not configured(provider):
        name = "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET" if provider == "google" else "MICROSOFT_CLIENT_ID / MICROSOFT_CLIENT_SECRET"
        raise HTTPException(503, f"{provider.title()} sign-in is not configured on this server. Set {name} (see README).")
    state = secrets.token_urlsafe(24)
    db.add(OAuthState(user_id=user.id, state=state, provider=provider))
    db.commit()
    s = get_settings()
    if provider == "google":
        q = {"client_id": s.google_client_id, "redirect_uri": redirect_uri("google"), "response_type": "code", "scope": GOOGLE_SCOPES,
             "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state}
        return f"{GOOGLE_AUTH}?{urlencode(q)}"
    q = {"client_id": s.microsoft_client_id, "redirect_uri": redirect_uri("microsoft"), "response_type": "code",
         "scope": MS_SCOPES, "response_mode": "query", "state": state}
    return f"{_ms('authorize')}?{urlencode(q)}"


def finish(db: Session, provider: str, code: str, state: str) -> User:
    st = db.scalar(select(OAuthState).where(OAuthState.state == state, OAuthState.provider == provider))
    if not st or utcnow() - aware(st.created_at) > timedelta(minutes=15):
        raise HTTPException(400, "Sign-in link expired. Please try again.")
    user = db.get(User, st.user_id)
    db.delete(st)
    s = get_settings()
    with http.client() as c:
        if provider == "google":
            r = c.post(GOOGLE_TOKEN, data={"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                           "redirect_uri": redirect_uri("google"), "grant_type": "authorization_code"})
        else:
            r = c.post(_ms("token"), data={"code": code, "client_id": s.microsoft_client_id, "client_secret": s.microsoft_client_secret,
                                           "redirect_uri": redirect_uri("microsoft"), "grant_type": "authorization_code", "scope": MS_SCOPES})
        r.raise_for_status()
        tok = r.json()
        tok["obtained_at"] = utcnow().isoformat()
        email = ""
        try:
            if provider == "google":
                email = c.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {tok['access_token']}"}).json().get("email", "")
            else:
                me = c.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
                email = me.get("mail") or me.get("userPrincipalName", "")
        except Exception:
            pass
    acct = db.scalar(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id, ConnectedAccount.provider == provider))
    if acct is None:
        acct = ConnectedAccount(user_id=user.id, provider=provider, token_encrypted="")
        db.add(acct)
    acct.token_encrypted = encrypt_json(tok)
    acct.account_email = email
    acct.scopes = tok.get("scope", GOOGLE_SCOPES if provider == "google" else MS_SCOPES)
    db.commit()
    return user


def _access_token(db: Session, acct: ConnectedAccount) -> str:
    tok = decrypt_json(acct.token_encrypted)
    from datetime import datetime
    age = (utcnow() - aware(datetime.fromisoformat(tok["obtained_at"]))).total_seconds()
    if age < int(tok.get("expires_in", 3600)) - 120:
        return tok["access_token"]
    if not tok.get("refresh_token"):
        raise HTTPException(412, f"Your {acct.provider.title()} connection expired. Please reconnect.")
    s = get_settings()
    with http.client() as c:
        if acct.provider == "google":
            r = c.post(GOOGLE_TOKEN, data={"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                           "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
        else:
            r = c.post(_ms("token"), data={"client_id": s.microsoft_client_id, "client_secret": s.microsoft_client_secret,
                                           "refresh_token": tok["refresh_token"], "grant_type": "refresh_token", "scope": MS_SCOPES})
    if r.status_code >= 400:
        raise HTTPException(412, f"Your {acct.provider.title()} connection expired. Please reconnect.")
    new = r.json()
    tok.update({k: v for k, v in new.items() if v})
    tok["obtained_at"] = utcnow().isoformat()
    acct.token_encrypted = encrypt_json(tok)
    db.commit()
    return tok["access_token"]


def account(db: Session, user_id: int, provider: str) -> ConnectedAccount:
    acct = db.scalar(select(ConnectedAccount).where(ConnectedAccount.user_id == user_id, ConnectedAccount.provider == provider))
    if not acct:
        raise HTTPException(412, f"Connect your {'Google' if provider == 'google' else 'Microsoft'} account first.")
    return acct


# ------------------------------------------------------------------ reading documents
def google_doc_id(url_or_id: str) -> str:
    m = re.search(r"/document/d/([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", url_or_id.strip()):
        return url_or_id.strip()
    raise HTTPException(422, "That doesn't look like a Google Docs link.")


def parse_google(doc: dict) -> tuple[str, list[dict]]:
    paras = []
    for el in doc.get("body", {}).get("content", []):
        p = el.get("paragraph")
        if not p:
            continue
        text = "".join(e.get("textRun", {}).get("content", "") for e in p.get("elements", [])).strip()
        if not text:
            continue
        style = p.get("paragraphStyle", {})
        named = style.get("namedStyleType", "NORMAL_TEXT")
        paras.append({"index": len(paras), "text": text, "style": named, "is_heading": named.startswith("HEADING") or named == "TITLE",
                      "heading_id": style.get("headingId")})
    return doc.get("title", "Google Doc"), paras


def fetch_google(db: Session, user_id: int, doc_id: str) -> tuple[str, list[dict]]:
    token = _access_token(db, account(db, user_id, "google"))
    with http.client() as c:
        r = c.get(DOCS_API + doc_id, headers={"Authorization": f"Bearer {token}"})
    if r.status_code in (403, 404):
        raise HTTPException(404, "Google Docs: the document wasn't found or your account can't read it.")
    r.raise_for_status()
    return parse_google(r.json())


def share_id(url: str) -> str:
    return "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def fetch_word(db: Session, user_id: int, ref: str) -> tuple[str, list[dict], str, str]:
    """Returns (title, paragraphs, item_path, web_url). Read-only GET calls only."""
    token = _access_token(db, account(db, user_id, "microsoft"))
    h = {"Authorization": f"Bearer {token}"}
    with http.client() as c:
        if ref.startswith("http"):
            meta = c.get(f"{GRAPH}/shares/{share_id(ref)}/driveItem", headers=h)
        elif ref.startswith("/drives/"):
            meta = c.get(f"{GRAPH}{ref}", headers=h)
        else:
            meta = c.get(f"{GRAPH}/me/drive/items/{ref}", headers=h)
        if meta.status_code in (403, 404):
            raise HTTPException(404, "OneDrive/SharePoint: the file wasn't found or your account can't read it.")
        meta.raise_for_status()
        m = meta.json()
        if not m.get("name", "").lower().endswith(".docx"):
            raise HTTPException(422, "Only Word .docx files can be connected.")
        drive = m.get("parentReference", {}).get("driveId")
        item_path = f"/drives/{drive}/items/{m['id']}" if drive else f"/me/drive/items/{m['id']}"
        content = c.get(f"{GRAPH}{item_path}/content", headers=h)
        content.raise_for_status()
    return m["name"].removesuffix(".docx"), paragraphs_from_docx(content.content), item_path, m.get("webUrl", "")


def _text(paras: list[dict]) -> str:
    return "\n\n".join(p["text"] for p in paras)


def fresh_snapshot(db: Session, user: User, doc: Document) -> dict:
    """Read the document now (read-only). Uploaded .docx files use the stored copy."""
    if doc.source == "google_docs":
        _, paras = fetch_google(db, user.id, doc.external_id)
    elif doc.source == "word" and doc.external_id:
        _, paras, _, _ = fetch_word(db, user.id, doc.external_id)
    else:  # uploaded .docx: the uploaded copy is the latest version Re-Focus AI has
        last = db.scalar(select(ExternalDocumentSnapshot).where(ExternalDocumentSnapshot.document_id == doc.id)
                         .order_by(ExternalDocumentSnapshot.captured_at.desc()))
        paras = last.paragraphs if last else [{"index": i, "text": t} for i, t in enumerate(p for p in (doc.content_text or "").split("\n\n") if p.strip())]
    return {"text": _text(paras), "paragraphs": paras}


def store_snapshot(db: Session, user: User, doc: Document, checkpoint_id: int | None = None, paras: list[dict] | None = None) -> ExternalDocumentSnapshot:
    if paras is None:
        paras = fresh_snapshot(db, user, doc)["paragraphs"]
    snap = ExternalDocumentSnapshot(user_id=user.id, document_id=doc.id, checkpoint_id=checkpoint_id, text=_text(paras), paragraphs=paras)
    db.add(snap)
    doc.content_text = snap.text
    doc.updated_at = utcnow()
    db.flush()
    return snap


def guess_position(db: Session, doc: Document, snap: ExternalDocumentSnapshot) -> dict:
    """AI Guess for where the user stopped: the last paragraph that changed since the previous snapshot."""
    prev = db.scalar(select(ExternalDocumentSnapshot).where(ExternalDocumentSnapshot.document_id == doc.id,
                                                            ExternalDocumentSnapshot.id < snap.id)
                     .order_by(ExternalDocumentSnapshot.id.desc()))
    paras = snap.paragraphs or []
    if not paras:
        return {"paragraph_text": "", "source": "ai_guess", "basis": "The document is empty."}
    old = {p["text"] for p in (prev.paragraphs if prev else [])}
    changed = [p for p in paras if p["text"] not in old] if prev else []
    target = changed[-1] if changed else paras[-1]
    heading = None
    for p in paras[: target["index"] + 1]:
        if p.get("is_heading") and p.get("heading_id"):
            heading = p["heading_id"]
    basis = "Last paragraph that changed since your previous checkpoint." if changed else "Last paragraph in the document (no earlier snapshot to compare)."
    return {"paragraph_index": target["index"], "paragraph_text": target["text"], "heading_id": heading, "source": "ai_guess", "basis": basis}
