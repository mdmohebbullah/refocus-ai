"""Time Away (15), Active Work Time (16)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, current_user, ensure_settings, get_principal, owned, owned_project
from ..models import TimeTrackingRecord, User, aware
from ..schemas import HeartbeatIn, TimeCorrectionIn
from ..serializers import iso
from ..timekeeping import heartbeat, summaries, time_status

router = APIRouter(prefix="/api/time", tags=["time"])


@router.post("/heartbeat")
def post_heartbeat(body: HeartbeatIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Sent only while the user is actively interacting (see frontend hooks/activity.ts and the extension)."""
    owned_project(db, body.project_id, p.user.id)
    prefs, priv = ensure_settings(db, p.user)
    if body.source == "extension" and (priv.private_mode or (p.device and not p.device.collection_enabled)):
        return {"recorded": False}
    sess = heartbeat(db, p.user.id, body.project_id, prefs, body.source)
    return {"recorded": True, "session_seconds": sess.active_seconds}


@router.get("/status")
def get_status(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prefs, _ = ensure_settings(db, user)
    return time_status(db, user.id, owned_project(db, project_id, user.id), prefs)


@router.get("/summary")
def get_summary(project_id: int | None = None, days: int = 7, tz_offset_minutes: int = 0,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if project_id:
        owned_project(db, project_id, user.id)
    days = max(1, min(days, 31))
    data = summaries(db, user.id, project_id, days, tz_offset_minutes)
    return {"days": data, "total_active_seconds": sum(d["active_seconds"] for d in data),
            "total_away_seconds": sum(d["away_seconds"] for d in data)}


@router.get("/records")
def list_records(project_id: int, limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    rs = db.scalars(select(TimeTrackingRecord).where(TimeTrackingRecord.user_id == user.id, TimeTrackingRecord.project_id == project_id)
                    .order_by(TimeTrackingRecord.started_at.desc()).limit(limit))
    return {"records": [{"id": r.id, "kind": r.kind, "started_at": iso(r.started_at), "ended_at": iso(r.ended_at), "seconds": r.seconds,
                         "source": r.source, "corrected": r.corrected, "note": r.note} for r in rs]}


@router.post("/records", status_code=201)
def add_record(body: TimeCorrectionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Manual correction: add time the app could not see (e.g. writing on paper)."""
    owned_project(db, body.project_id, user.id)
    start, end = aware(body.started_at), aware(body.ended_at)
    if end <= start:
        raise HTTPException(422, "End must be after start")
    r = TimeTrackingRecord(user_id=user.id, project_id=body.project_id, kind=body.kind, started_at=start, ended_at=end,
                           seconds=int((end - start).total_seconds()), source="manual", corrected=True, note=body.note)
    db.add(r)
    db.commit()
    return {"id": r.id, "seconds": r.seconds}


@router.patch("/records/{record_id}")
def edit_record(record_id: int, body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db, TimeTrackingRecord, record_id, user.id)
    if "kind" in body and body["kind"] in ("active", "away"):
        r.kind = body["kind"]
    if "seconds" in body:
        r.seconds = max(0, int(body["seconds"]))
    if "note" in body:
        r.note = str(body["note"])[:500]
    r.corrected = True
    db.commit()
    return {"id": r.id, "kind": r.kind, "seconds": r.seconds, "corrected": True}


@router.delete("/records/{record_id}", status_code=204)
def delete_record(record_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, TimeTrackingRecord, record_id, user.id))
    db.commit()
