"""Browser Tabs (Feature 3), Last 60 Minutes (4), device pairing for the extension."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import Principal, account_user, current_user, ensure_settings, get_principal, owned
from ..models import ActivityEvent, BrowserTab, DeviceConnection, PrivacySettings, User, aware, utcnow
from ..privacy import domain_of, effective_exclusions, is_excluded
from ..schemas import (ActivityBatchIn, ActivitySelectIn, DeviceIn, DevicePatch, TabSelectIn, TabSyncIn)
from ..security import hash_token, new_device_token

router = APIRouter(prefix="/api", tags=["browser"])


def purge_expired(db: Session, user_id: int, priv: PrivacySettings) -> int:
    """History retention: delete browser activity older than the user's retention window."""
    cutoff = utcnow() - timedelta(days=priv.history_retention_days or 30)
    r = db.execute(delete(ActivityEvent).where(ActivityEvent.user_id == user_id, ActivityEvent.occurred_at < cutoff))
    return r.rowcount or 0


def collection_allowed(p: Principal, priv: PrivacySettings) -> bool:
    if priv.private_mode or not priv.activity_collection:
        return False
    if p.device is not None and not p.device.collection_enabled:
        return False
    return True


# ------------------------------------------------------------------ devices
@router.post("/devices", status_code=201)
def pair_device(body: DeviceIn, user: User = Depends(account_user), db: Session = Depends(get_db)):
    token = new_device_token()
    d = DeviceConnection(user_id=user.id, name=body.name, kind=body.kind, token_hash=hash_token(token))
    db.add(d)
    db.commit()
    return {"id": d.id, "name": d.name, "token": token, "note": "Copy this token into the Re-Focus AI extension. It is shown only once."}


@router.get("/devices")
def list_devices(user: User = Depends(account_user), db: Session = Depends(get_db)):
    ds = db.scalars(select(DeviceConnection).where(DeviceConnection.user_id == user.id).order_by(DeviceConnection.created_at)).all()
    return {"devices": [{"id": d.id, "name": d.name, "kind": d.kind, "collection_enabled": d.collection_enabled,
                         "content_access": d.content_access, "last_seen_at": S.iso(d.last_seen_at), "created_at": S.iso(d.created_at)} for d in ds]}


@router.patch("/devices/{device_id}")
def update_device(device_id: int, body: DevicePatch, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = owned(db, DeviceConnection, device_id, p.user.id)
    if p.device is not None and p.device.id != d.id:
        raise HTTPException(403, "A device can only change its own settings")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(d, k, v)
    if not d.content_access:  # turning content access off removes stored page excerpts from this device
        for t in db.scalars(select(BrowserTab).where(BrowserTab.device_id == d.id)):
            t.content_excerpt, t.content_available = None, False
    db.commit()
    return {"id": d.id, "collection_enabled": d.collection_enabled, "content_access": d.content_access}


@router.delete("/devices/{device_id}", status_code=204)
def revoke_device(device_id: int, user: User = Depends(account_user), db: Session = Depends(get_db)):
    d = owned(db, DeviceConnection, device_id, user.id)
    db.delete(d)
    db.commit()


# ------------------------------------------------------------------ tabs
@router.post("/tabs/sync")
def sync_tabs(body: TabSyncIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Called by the extension with the currently open tabs (metadata; page content only with content access)."""
    if p.device is None:
        raise HTTPException(403, "Only a paired extension can send tabs")
    _, priv = ensure_settings(db, p.user)
    if not collection_allowed(p, priv):
        db.execute(delete(BrowserTab).where(BrowserTab.device_id == p.device.id))
        db.commit()
        return {"stored": 0, "collection": "off"}
    approved = set(priv.approved_domains or []) if priv.remember_tab_preferences else set()
    seen = set()
    stored = 0
    for t in body.tabs:
        excluded = is_excluded(t.url, priv, t.has_password_field)
        dom = domain_of(t.url)
        row = db.scalar(select(BrowserTab).where(BrowserTab.device_id == p.device.id, BrowserTab.tab_id == t.tab_id))
        if excluded:
            # Excluded tabs never store titles, URLs or contents — only that an excluded tab exists.
            if row:
                db.delete(row)
            continue
        if row is None:
            row = BrowserTab(user_id=p.user.id, device_id=p.device.id, tab_id=t.tab_id, selected=dom in approved)
            db.add(row)
        row.window_id, row.title, row.url, row.domain = t.window_id, t.title[:1000], t.url[:2000], dom
        row.fav_icon_url, row.status, row.last_seen_at = t.fav_icon_url, t.status, utcnow()
        if p.device.content_access and t.content_excerpt:
            row.content_excerpt, row.content_available = t.content_excerpt[:4000], True
        else:
            row.content_excerpt, row.content_available = None, False
        seen.add(t.tab_id)
        stored += 1
    db.execute(delete(BrowserTab).where(BrowserTab.device_id == p.device.id, BrowserTab.tab_id.not_in(seen or {-1})))
    db.commit()
    return {"stored": stored, "excluded": len(body.tabs) - stored, "collection": "on"}


@router.get("/tabs")
def list_tabs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, priv = ensure_settings(db, user)
    tabs = db.scalars(select(BrowserTab).where(BrowserTab.user_id == user.id).order_by(BrowserTab.window_id, BrowserTab.tab_id)).all()
    return {"tabs": [S.tab(t, is_excluded(t.url, priv)) for t in tabs],
            "collection": "private_mode" if priv.private_mode else ("on" if priv.activity_collection else "off"),
            "remember_preferences": priv.remember_tab_preferences}


@router.post("/tabs/select")
def select_tabs(body: TabSelectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Select / deselect individual tabs (or all, by passing every id)."""
    _, priv = ensure_settings(db, user)
    changed = 0
    approved = set(priv.approved_domains or [])
    for tid in body.tab_ids:
        t = owned(db, BrowserTab, tid, user.id)
        if is_excluded(t.url, priv):
            continue  # excluded tabs can never be selected
        t.selected = body.selected
        if body.project_id is not None:
            t.project_id = body.project_id
        if priv.remember_tab_preferences and t.domain:
            approved.add(t.domain) if body.selected else approved.discard(t.domain)
        changed += 1
    priv.approved_domains = sorted(approved)
    db.commit()
    return {"changed": changed}


@router.post("/tabs/exclude-site")
def exclude_site(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Exclude a website: removes stored tabs and activity for it and blocks it from now on."""
    _, priv = ensure_settings(db, user)
    dom = (body.get("domain") or domain_of(body.get("url"))).lower().removeprefix("www.")
    if not dom:
        raise HTTPException(422, "domain required")
    priv.excluded_domains = sorted(set(priv.excluded_domains or []) | {dom})
    priv.approved_domains = [d for d in (priv.approved_domains or []) if d != dom]
    db.execute(delete(BrowserTab).where(BrowserTab.user_id == user.id, (BrowserTab.domain == dom) | BrowserTab.domain.like(f"%.{dom}")))
    for a in db.scalars(select(ActivityEvent).where(ActivityEvent.user_id == user.id,
                                                     (ActivityEvent.domain == dom) | ActivityEvent.domain.like(f"%.{dom}"))):
        a.excluded, a.selected, a.title, a.url, a.content_excerpt = True, False, None, None, None
    db.commit()
    return {"excluded_domains": effective_exclusions(priv)}


# ------------------------------------------------------------------ activity (last 60 minutes)
@router.post("/activity/batch")
def ingest_activity(body: ActivityBatchIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    _, priv = ensure_settings(db, p.user)
    if not collection_allowed(p, priv):
        return {"stored": 0, "collection": "off"}
    stored = dropped = 0
    for e in body.events:
        dom = domain_of(e.url)
        when = aware(e.occurred_at)
        dup = db.scalar(select(ActivityEvent.id).where(ActivityEvent.user_id == p.user.id, ActivityEvent.url == e.url, ActivityEvent.occurred_at == when))
        if dup:
            continue
        if is_excluded(e.url, priv, e.has_password_field):
            dropped += 1  # sensitive/excluded visits are dropped entirely, not stored
            continue
        db.add(ActivityEvent(user_id=p.user.id, project_id=e.project_id, device_id=p.device.id if p.device else None,
                             kind="page_visit", title=e.title[:1000], url=e.url[:2000], domain=dom, occurred_at=when,
                             selected=dom in set(priv.approved_domains or []) or not priv.remember_tab_preferences))
        stored += 1
    db.flush()
    purge_expired(db, p.user.id, priv)
    db.commit()
    return {"stored": stored, "dropped_excluded": dropped}


@router.get("/activity")
def list_activity(minutes: int = 60, start: datetime | None = None, end: datetime | None = None, project_id: int | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Recorded browser metadata in a window (15/30/60 minutes or custom). Never page content or keystrokes."""
    _, priv = ensure_settings(db, user)
    purge_expired(db, user.id, priv)
    db.commit()
    end_at = aware(end) or utcnow()
    start_at = aware(start) or end_at - timedelta(minutes=max(1, min(minutes, 60 * 24 * 7)))
    q = select(ActivityEvent).where(ActivityEvent.user_id == user.id, ActivityEvent.occurred_at >= start_at, ActivityEvent.occurred_at <= end_at)
    if project_id:
        q = q.where((ActivityEvent.project_id == project_id) | ActivityEvent.project_id.is_(None))
    events = []
    for a in db.scalars(q.order_by(ActivityEvent.occurred_at.desc())):
        if not a.excluded and is_excluded(a.url, priv):
            a.excluded, a.selected = True, False
        events.append(S.activity(a))
    return {"events": events, "start": start_at.isoformat(), "end": end_at.isoformat(),
            "note": "Only page titles, addresses and times are recorded — not page content, keystrokes, or thoughts."}


@router.post("/activity/select")
def select_activity(body: ActivitySelectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = 0
    for i in body.ids:
        a = owned(db, ActivityEvent, i, user.id)
        if a.excluded:
            continue
        a.selected = body.selected
        n += 1
    db.commit()
    return {"changed": n}


@router.post("/activity/assign")
def assign_activity(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Link activity events to a project (Feature 2: link browser activity)."""
    for i in body.get("ids", []):
        owned(db, ActivityEvent, i, user.id).project_id = body.get("project_id")
    db.commit()
    return {"ok": True}
