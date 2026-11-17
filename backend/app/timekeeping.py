"""Active work time, time away, and the suggested help level.

Active time only accumulates from heartbeats sent while the user is actually interacting
(focused window + recent input in the web app, or an active, non-idle tab in the extension).
A gap longer than the inactivity threshold is recorded as time away, not active time.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (Project, TimeTrackingRecord, UserPreferences, WorkSession, aware, utcnow)

# (upper bound in minutes, recommended resume, suggested help level)
TIME_AWAY_TABLE = [
    (15, "Quick reminder", "brief"),
    (60, "Brief context and unfinished thought", "brief"),
    (240, "Goal, sources, and next step", "balanced"),
    (1440, "Detailed checkpoint summary", "detailed"),
    (None, "Comprehensive summary", "detailed"),
]


def suggest_for_minutes(minutes: float | None) -> dict:
    if minutes is None:
        return {"recommended_resume": "Comprehensive summary", "suggested_help_level": "detailed"}
    for bound, label, level in TIME_AWAY_TABLE:
        if bound is None or minutes < bound:
            return {"recommended_resume": label, "suggested_help_level": level}
    raise AssertionError


def effective_help_level(prefs: UserPreferences | None, minutes_away: float | None) -> dict:
    sug = suggest_for_minutes(minutes_away)
    chosen = prefs.help_level if prefs and prefs.help_level else None
    return {**sug, "help_level": chosen or sug["suggested_help_level"],
            "help_level_source": "user_preference" if chosen else "time_away_suggestion"}


def open_session(db: Session, user_id: int, project_id: int) -> WorkSession | None:
    return db.scalar(select(WorkSession).where(WorkSession.user_id == user_id, WorkSession.project_id == project_id,
                                               WorkSession.status == "active").order_by(WorkSession.id.desc()))


def heartbeat(db: Session, user_id: int, project_id: int, prefs: UserPreferences, source: str = "app",
              now: datetime | None = None) -> WorkSession:
    """Record that the user is actively working on a project right now."""
    now = now or utcnow()
    gap_limit = timedelta(minutes=prefs.inactivity_gap_minutes or 5)
    project = db.get(Project, project_id)
    sess = open_session(db, user_id, project_id)
    last_active = aware(project.last_active_at) if project else None

    if sess and now - aware(sess.last_active_at) <= gap_limit:
        delta = now - aware(sess.last_active_at)
        secs = max(0, int(delta.total_seconds()))
        sess.active_seconds += secs
        if secs:
            db.add(TimeTrackingRecord(user_id=user_id, project_id=project_id, session_id=sess.id, kind="active",
                                      started_at=aware(sess.last_active_at), ended_at=now, seconds=secs, source=source))
        sess.last_active_at = now
    else:
        if sess:  # stale session: close it at its last activity
            sess.status = "ended"
            sess.ended_at = sess.last_active_at
        if last_active and now - last_active > gap_limit:
            away = int((now - last_active).total_seconds())
            db.add(TimeTrackingRecord(user_id=user_id, project_id=project_id, kind="away", started_at=last_active,
                                      ended_at=now, seconds=away, source=source))
        sess = WorkSession(user_id=user_id, project_id=project_id, started_at=now, last_active_at=now)
        db.add(sess)
    if project:
        project.last_active_at = now
    db.commit()
    return sess


def time_status(db: Session, user_id: int, project: Project, prefs: UserPreferences, now: datetime | None = None) -> dict:
    now = now or utcnow()
    last_active = aware(project.last_active_at)
    gap_limit = timedelta(minutes=prefs.inactivity_gap_minutes or 5)
    sess = open_session(db, user_id, project.id)
    active_now = bool(last_active and now - last_active <= gap_limit)
    minutes_away = None if last_active is None else (0.0 if active_now else (now - last_active).total_seconds() / 60)
    total = sum(r.seconds for r in db.scalars(select(TimeTrackingRecord).where(
        TimeTrackingRecord.user_id == user_id, TimeTrackingRecord.project_id == project.id, TimeTrackingRecord.kind == "active")))
    return {
        "project_id": project.id,
        "last_active_at": last_active.isoformat() if last_active else None,
        "returned_at": now.isoformat(),
        "minutes_away": None if minutes_away is None else round(minutes_away, 1),
        "active_now": active_now,
        "current_session_seconds": sess.active_seconds if (sess and active_now) else 0,
        "total_recorded_seconds": total,
        "basis": "Recorded inactivity in Re-Focus AI for this project, not a verified absence from all work.",
        **effective_help_level(prefs, minutes_away),
    }


def summaries(db: Session, user_id: int, project_id: int | None, days: int, tz_offset_minutes: int = 0) -> list[dict]:
    """Daily active/away totals for the last `days` days, in the user's timezone."""
    now = utcnow()
    start = now - timedelta(days=days)
    q = select(TimeTrackingRecord).where(TimeTrackingRecord.user_id == user_id, TimeTrackingRecord.started_at >= start)
    if project_id:
        q = q.where(TimeTrackingRecord.project_id == project_id)
    buckets: dict[str, dict] = {}
    for i in range(days):
        day = (now + timedelta(minutes=tz_offset_minutes) - timedelta(days=days - 1 - i)).date().isoformat()
        buckets[day] = {"date": day, "active_seconds": 0, "away_seconds": 0}
    for r in db.scalars(q):
        day = (aware(r.started_at) + timedelta(minutes=tz_offset_minutes)).date().isoformat()
        if day in buckets:
            buckets[day][f"{r.kind}_seconds"] += r.seconds
    return list(buckets.values())
