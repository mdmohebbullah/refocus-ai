"""Smart Dashboard (Feature 1)."""
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..ai import service as ai
from ..db import get_db
from ..deps import current_user, ensure_settings
from ..models import (ActivityEvent, Checkpoint, DeviceConnection, Project, Task, UnfinishedThought, User, aware, utcnow)
from ..privacy import is_excluded
from ..timekeeping import time_status
from .projects import pinned_ids

router = APIRouter(prefix="/api", tags=["dashboard"])


def browser_status(db: Session, user_id: int, privacy) -> dict:
    devices = db.scalars(select(DeviceConnection).where(DeviceConnection.user_id == user_id, DeviceConnection.kind == "extension")).all()
    now = utcnow()
    online = [d for d in devices if d.last_seen_at and now - aware(d.last_seen_at) < timedelta(minutes=3)]
    if privacy.private_mode:
        state = "private_mode"
    elif not privacy.activity_collection:
        state = "collection_off"
    elif online:
        state = "connected"
    elif devices:
        state = "not_seen_recently"
    else:
        state = "not_connected"
    return {"state": state, "devices": [{"id": d.id, "name": d.name, "collection_enabled": d.collection_enabled,
                                         "last_seen_at": S.iso(d.last_seen_at)} for d in devices]}


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    prefs, priv = ensure_settings(db, user)
    pins = pinned_ids(db, user.id, "project")
    projects = db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())).all()
    project = next((p for p in projects if p.id == prefs.current_project_id), projects[0] if projects else None)
    out = {"user": {"name": user.name}, "project": None, "recent_projects": [S.project(p, p.id in pins) for p in projects[:6]],
           "browser": browser_status(db, user.id, priv)}
    if not project:
        return out
    cp = db.scalar(select(Checkpoint).where(Checkpoint.project_id == project.id).order_by(Checkpoint.id.desc()))
    thought = db.scalar(select(UnfinishedThought).where(UnfinishedThought.project_id == project.id, UnfinishedThought.completed.is_(False))
                        .order_by(UnfinishedThought.updated_at.desc()))
    step = None
    if cp or thought or project.goal:
        _, s = ai.resume_suggestions(db, user.id, project.id, cp)
        step = ai.serialize(s)
    acts = []
    if priv.activity_collection and not priv.private_mode:
        for a in db.scalars(select(ActivityEvent).where(ActivityEvent.user_id == user.id, ActivityEvent.selected.is_(True),
                                                       ActivityEvent.excluded.is_(False)).order_by(ActivityEvent.occurred_at.desc()).limit(10)):
            if not is_excluded(a.url, priv):
                acts.append(S.activity(a))
    history = []
    for c in db.scalars(select(Checkpoint).where(Checkpoint.project_id == project.id).order_by(Checkpoint.id.desc()).limit(4)):
        history.append({"kind": "checkpoint", "id": c.id, "title": c.label, "at": S.iso(c.created_at)})
    for t in db.scalars(select(UnfinishedThought).where(UnfinishedThought.project_id == project.id).order_by(UnfinishedThought.created_at.desc()).limit(4)):
        history.append({"kind": "thought", "id": t.id, "title": (t.thinking or t.next_plan or t.missing)[:90], "at": S.iso(t.created_at)})
    history.sort(key=lambda h: h["at"] or "", reverse=True)
    tasks = db.scalars(select(Task).where(Task.project_id == project.id, Task.status == "open").order_by(Task.created_at.desc()).limit(6)).all()
    out.update({
        "project": S.project(project, project.id in pins),
        "last_checkpoint": S.checkpoint(cp) if cp else None,
        "current_thought": S.thought(thought) if thought else None,
        "goal": {"text": (cp.goal if cp and cp.goal else project.goal), "provenance_label": "Saved by You"} if (project.goal or (cp and cp.goal)) else None,
        "next_step": step,
        "recent_activity": acts[:5],
        "time": time_status(db, user.id, project, prefs),
        "recent_history": history[:6],
        "pending_tasks": [S.task(t) for t in tasks],
    })
    return out
