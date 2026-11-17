"""History (6), Smart Search (21), document versions & comparison (19), sync status (23)."""
import hashlib
import re
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import provenance as P
from .. import serializers as S
from ..ai.provider import STOPWORDS, call_with_fallback
from ..db import get_db
from ..deps import account_user, current_user, ensure_settings, owned
from ..models import (ActivityEvent, AISuggestion, Checkpoint, Document, DocumentVersion, ExternalDocumentSnapshot, Project,
                      Reference, SourceSelection, Task, UnfinishedThought, User, UserNote, WorkSession, aware, utcnow)
from ..privacy import is_excluded
from .projects import snapshot_version

router = APIRouter(prefix="/api", tags=["history"])


def _day_bounds(d_from: date | None, d_to: date | None, tz_offset_minutes: int):
    off = timedelta(minutes=tz_offset_minutes)
    start = datetime.combine(d_from, time.min, tzinfo=timezone.utc) - off if d_from else None
    end = datetime.combine(d_to, time.max, tzinfo=timezone.utc) - off if d_to else None
    return start, end


@router.get("/history")
def history(project_id: int | None = None, q: str = "", website: str = "", date_from: date | None = None, date_to: date | None = None,
            kinds: str = "work,checkpoint,thought,browser,source", tz_offset_minutes: int = 0, limit: int = 200,
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, priv = ensure_settings(db, user)
    from .browser import purge_expired
    purge_expired(db, user.id, priv)
    db.commit()
    start, end = _day_bounds(date_from, date_to, tz_offset_minutes)
    want = set(kinds.split(","))
    like = f"%{q}%" if q else None
    items: list[dict] = []
    projects = {p.id: p.name for p in db.scalars(select(Project).where(Project.user_id == user.id))}

    def rng(col):
        conds = []
        if start:
            conds.append(col >= start)
        if end:
            conds.append(col <= end)
        return conds

    if "work" in want and not website:
        st = select(WorkSession).where(WorkSession.user_id == user.id, *rng(WorkSession.started_at))
        if project_id:
            st = st.where(WorkSession.project_id == project_id)
        for w in db.scalars(st.order_by(WorkSession.started_at.desc()).limit(limit)):
            if like and q.lower() not in projects.get(w.project_id, "").lower():
                continue
            items.append({"kind": "work", "group": "Recorded work session", "id": w.id, "project_id": w.project_id,
                          "project": projects.get(w.project_id), "title": f"Worked on {projects.get(w.project_id, 'project')}",
                          "detail": f"{round(w.active_seconds / 60)} min active", "at": S.iso(w.started_at), "end": S.iso(w.ended_at or w.last_active_at),
                          **P.item(P.RECORDED_ACTIVITY)})
    if "checkpoint" in want and not website:
        st = select(Checkpoint).where(Checkpoint.user_id == user.id, *rng(Checkpoint.created_at))
        if project_id:
            st = st.where(Checkpoint.project_id == project_id)
        if like:
            st = st.where(or_(Checkpoint.label.ilike(like), Checkpoint.goal.ilike(like)))
        for c in db.scalars(st.order_by(Checkpoint.created_at.desc()).limit(limit)):
            items.append({"kind": "checkpoint", "group": "Recorded work session", "id": c.id, "project_id": c.project_id, "project": projects.get(c.project_id),
                          "title": c.label, "detail": (c.position or {}).get("paragraph_text", "")[-120:], "at": S.iso(c.created_at), **P.item(P.SAVED_BY_YOU)})
    if "thought" in want and not website:
        st = select(UnfinishedThought).where(UnfinishedThought.user_id == user.id, *rng(UnfinishedThought.created_at))
        if project_id:
            st = st.where(UnfinishedThought.project_id == project_id)
        if like:
            st = st.where(or_(UnfinishedThought.thinking.ilike(like), UnfinishedThought.missing.ilike(like), UnfinishedThought.next_plan.ilike(like)))
        for t in db.scalars(st.order_by(UnfinishedThought.created_at.desc()).limit(limit)):
            items.append({"kind": "thought", "group": "Recorded work session", "id": t.id, "project_id": t.project_id, "project": projects.get(t.project_id),
                          "title": (t.thinking or t.next_plan or t.missing)[:140], "detail": "Completed" if t.completed else "", "at": S.iso(t.created_at),
                          **P.item(P.SAVED_BY_YOU)})
    if "source" in want:
        st = select(SourceSelection).join(Checkpoint, SourceSelection.checkpoint_id == Checkpoint.id).where(SourceSelection.user_id == user.id, *rng(Checkpoint.created_at))
        if project_id:
            st = st.where(SourceSelection.project_id == project_id)
        if like:
            st = st.where(or_(SourceSelection.title.ilike(like), SourceSelection.url.ilike(like)))
        if website:
            st = st.where(SourceSelection.url.ilike(f"%{website}%"))
        for s, created in db.execute(st.add_columns(Checkpoint.created_at).limit(limit)):
            items.append({"kind": "source", "group": "Previously selected source", "id": s.id, "project_id": s.project_id, "project": projects.get(s.project_id),
                          "title": s.title or s.url, "url": s.url, "detail": f"Kept at checkpoint {s.checkpoint_id}", "at": S.iso(created),
                          **P.item(P.SAVED_BY_YOU if s.kind == "reference" else P.RECORDED_ACTIVITY)})
    if "browser" in want:
        st = select(ActivityEvent).where(ActivityEvent.user_id == user.id, ActivityEvent.excluded.is_(False), *rng(ActivityEvent.occurred_at))
        if project_id:
            st = st.where(or_(ActivityEvent.project_id == project_id, ActivityEvent.project_id.is_(None)))
        if like:
            st = st.where(or_(ActivityEvent.title.ilike(like), ActivityEvent.url.ilike(like)))
        if website:
            st = st.where(ActivityEvent.domain.ilike(f"%{website}%"))
        for a in db.scalars(st.order_by(ActivityEvent.occurred_at.desc()).limit(limit)):
            if is_excluded(a.url, priv):
                continue
            items.append({"kind": "browser", "group": "Browser metadata", "id": a.id, "project_id": a.project_id, "project": projects.get(a.project_id),
                          "title": a.title, "url": a.url, "detail": a.domain, "at": S.iso(a.occurred_at), "selected": a.selected,
                          **P.item(P.RECORDED_ACTIVITY)})
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return {"items": items[:limit], "count": len(items)}


@router.get("/history/calendar")
def calendar(month: str, project_id: int | None = None, tz_offset_minutes: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        y, m = map(int, month.split("-"))
        first = date(y, m, 1)
    except ValueError:
        raise HTTPException(422, "month must be YYYY-MM")
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    start, end = _day_bounds(first, nxt - timedelta(days=1), tz_offset_minutes)
    off = timedelta(minutes=tz_offset_minutes)
    days: dict[str, dict] = {}

    def bump(dt, key):
        d = (aware(dt) + off).date().isoformat()
        days.setdefault(d, {"date": d, "work": 0, "browser": 0})[key] += 1
    for model, col, key in ((WorkSession, WorkSession.started_at, "work"), (Checkpoint, Checkpoint.created_at, "work"),
                            (UnfinishedThought, UnfinishedThought.created_at, "work"), (ActivityEvent, ActivityEvent.occurred_at, "browser")):
        st = select(col).where(model.user_id == user.id, col >= start, col <= end)
        if project_id and hasattr(model, "project_id"):
            st = st.where(model.project_id == project_id)
        if model is ActivityEvent:
            st = st.where(ActivityEvent.excluded.is_(False))
        for (dt,) in db.execute(st):
            bump(dt, key)
    return {"month": month, "days": sorted(days.values(), key=lambda d: d["date"])}


@router.delete("/activity/{event_id}", status_code=204)
def delete_activity(event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, ActivityEvent, event_id, user.id))
    db.commit()


@router.post("/history/clear")
def clear_history(body: dict, user: User = Depends(account_user), db: Session = Depends(get_db)):
    """Clear a history range. Browser metadata and work-session logs only; checkpoints/thoughts are deleted individually."""
    try:
        start = aware(datetime.fromisoformat(body["start"]))
        end = aware(datetime.fromisoformat(body["end"]))
    except (KeyError, ValueError):
        raise HTTPException(422, "start and end (ISO datetimes) are required")
    kinds = set(body.get("kinds") or ["browser"])
    removed = {}
    if "browser" in kinds:
        removed["browser"] = db.execute(delete(ActivityEvent).where(ActivityEvent.user_id == user.id, ActivityEvent.occurred_at >= start,
                                                                    ActivityEvent.occurred_at <= end)).rowcount
    if "work" in kinds:
        removed["work"] = db.execute(delete(WorkSession).where(WorkSession.user_id == user.id, WorkSession.started_at >= start,
                                                               WorkSession.started_at <= end)).rowcount
    db.commit()
    return {"removed": removed}


# ------------------------------------------------------------------ smart search
TIME_HINTS = {"today": 0, "yesterday": 1, "last week": 7, "this week": 7, "last month": 30}
TYPE_HINTS = {
    "article": {"activity", "reference"}, "paper": {"activity", "reference"}, "source": {"reference", "activity"}, "sources": {"reference", "activity"},
    "opened": {"activity"}, "visited": {"activity"}, "page": {"activity"}, "idea": {"thought"}, "ideas": {"thought"},
    "thought": {"thought"}, "thoughts": {"thought"}, "unfinished": {"thought"}, "note": {"note"}, "notes": {"note"},
    "checkpoint": {"checkpoint"}, "stopped": {"checkpoint"}, "task": {"task"}, "tasks": {"task"}, "saved": {"reference", "note", "thought"},
}
FILLER = STOPWORDS | {"find", "show", "my", "which", "did", "for", "the", "about", "i", "opened", "saved", "today", "yesterday", "last", "week",
                      "month", "this", "research", "article", "paper", "source", "sources", "idea", "ideas", "unfinished", "thought", "thoughts",
                      "note", "notes", "visited", "page", "checkpoint", "stopped", "task", "tasks", "me", "all"}


def parse_query(q: str, tz_offset_minutes: int):
    low = q.lower()
    since = until = None
    now_local = utcnow() + timedelta(minutes=tz_offset_minutes)
    for phrase, days in TIME_HINTS.items():
        if phrase in low:
            day0 = (now_local - timedelta(days=days)).date()
            since = datetime.combine(day0, time.min, tzinfo=timezone.utc) - timedelta(minutes=tz_offset_minutes)
            if phrase == "yesterday":
                until = since + timedelta(days=1)
            break
    types: set[str] = set()
    for w in re.findall(r"[a-z]+", low):
        types |= TYPE_HINTS.get(w, set())
    terms = [w for w in re.findall(r"[a-z0-9][a-z0-9\-]+", low) if w not in FILLER]
    return {"since": since, "until": until, "types": types, "terms": terms}


@router.get("/search")
def search(q: str, project_id: int | None = None, use_ai: bool = True, tz_offset_minutes: int = 0,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, priv = ensure_settings(db, user)
    parsed = parse_query(q, tz_offset_minutes)
    projects_all = list(db.scalars(select(Project).where(Project.user_id == user.id)))
    # "…about the literature review" → scope to the project whose name contains those words.
    if not project_id and parsed["terms"]:
        for p in projects_all:
            name = p.name.lower()
            used = [t for t in parsed["terms"] if t in name]
            if len(used) >= 2 or (used and len(parsed["terms"]) == 1):
                project_id = p.id
                parsed["terms"] = [t for t in parsed["terms"] if t not in used]
                parsed["project_scope"] = p.name
                break
    types = parsed["types"] or {"thought", "note", "reference", "activity", "checkpoint", "task", "document"}
    projects = {p.id: p.name for p in projects_all}

    def run(terms: list[str]) -> list[dict]:
        out = []

        def ok_time(dt):
            dt = aware(dt)
            return (not parsed["since"] or dt >= parsed["since"]) and (not parsed["until"] or dt < parsed["until"])

        def hit(text: str) -> int:
            """Number of query terms found (0 = no match). With no terms, everything matches."""
            t = (text or "").lower()
            return sum(term in t for term in terms) if terms else 1

        def scope(st, model):
            st = st.where(model.user_id == user.id)
            return st.where(model.project_id == project_id) if project_id and hasattr(model, "project_id") else st

        if "thought" in types:
            for t in db.scalars(scope(select(UnfinishedThought), UnfinishedThought)):
                if ok_time(t.created_at) and hit(f"{t.thinking} {t.missing} {t.next_plan}"):
                    out.append({"type": "thought", "id": t.id, "project_id": t.project_id, "title": (t.thinking or t.next_plan or t.missing)[:160],
                                "snippet": t.missing, "at": S.iso(t.created_at), **P.item(P.SAVED_BY_YOU)})
        if "note" in types:
            for n in db.scalars(scope(select(UserNote), UserNote)):
                if ok_time(n.created_at) and hit(f"{n.title} {n.body}"):
                    out.append({"type": "note", "id": n.id, "project_id": n.project_id, "title": n.title or n.body[:80], "snippet": n.body[:200],
                                "at": S.iso(n.updated_at), **P.item(P.SAVED_BY_YOU)})
        if "reference" in types:
            for r in db.scalars(scope(select(Reference), Reference)):
                if ok_time(r.created_at) and hit(f"{r.title} {r.authors} {r.why_saved} {r.url or ''}"):
                    out.append({"type": "reference", "id": r.id, "project_id": r.project_id, "title": r.title, "url": r.url,
                                "snippet": r.why_saved, "at": S.iso(r.created_at), **P.item(P.SAVED_BY_YOU)})
        if "activity" in types and not priv.private_mode:
            st = select(ActivityEvent).where(ActivityEvent.user_id == user.id, ActivityEvent.excluded.is_(False))
            if project_id:
                st = st.where(or_(ActivityEvent.project_id == project_id, ActivityEvent.project_id.is_(None)))
            for a in db.scalars(st.order_by(ActivityEvent.occurred_at.desc()).limit(2000)):
                if ok_time(a.occurred_at) and hit(f"{a.title} {a.url}") and not is_excluded(a.url, priv):
                    out.append({"type": "activity", "id": a.id, "project_id": a.project_id, "title": a.title, "url": a.url,
                                "snippet": a.domain, "at": S.iso(a.occurred_at), **P.item(P.RECORDED_ACTIVITY)})
        if "checkpoint" in types:
            for c in db.scalars(scope(select(Checkpoint), Checkpoint)):
                if ok_time(c.created_at) and hit(f"{c.label} {c.goal} {(c.position or {}).get('paragraph_text', '')}"):
                    out.append({"type": "checkpoint", "id": c.id, "project_id": c.project_id, "title": c.label,
                                "snippet": (c.position or {}).get("paragraph_text", "")[-160:], "at": S.iso(c.created_at), **P.item(P.SAVED_BY_YOU)})
        if "task" in types:
            for t in db.scalars(scope(select(Task), Task)):
                if ok_time(t.created_at) and hit(t.title):
                    out.append({"type": "task", "id": t.id, "project_id": t.project_id, "title": t.title, "snippet": t.status,
                                "at": S.iso(t.created_at), **S.task(t)})
        if "document" in types:
            for d in db.scalars(scope(select(Document), Document)):
                if hit(f"{d.title} {d.content_text}"):
                    text = d.content_text or ""
                    i = text.lower().find(terms[0]) if terms else 0
                    out.append({"type": "document", "id": d.id, "project_id": d.project_id, "title": d.title,
                                "snippet": text[max(0, i - 60): i + 140] if terms else text[:140], "at": S.iso(d.updated_at),
                                **P.item(P.SAVED_BY_YOU)})
        for o in out:
            o["project"] = projects.get(o.get("project_id"))
            blob = " ".join(str(o.get(k) or "") for k in ("title", "snippet", "url")).lower()
            o["score"] = sum(term in blob for term in terms) if terms else 1
        out.sort(key=lambda o: (o["score"], o.get("at") or ""), reverse=True)
        return out

    stored = run(parsed["terms"])
    for s in stored:
        s["match"] = "stored_record"
        s["match_label"] = "Matches your saved records"
    inferred: list[dict] = []
    provider = None
    if use_ai and parsed["terms"]:
        related, provider = call_with_fallback("related_terms", q)
        seen = {(s["type"], s["id"]) for s in stored}
        for term in related[:5]:
            for r in run([term]):
                if (r["type"], r["id"]) not in seen:
                    seen.add((r["type"], r["id"]))
                    r.update({"match": "ai_inferred", "match_label": f"AI-inferred association (related term “{term}”)",
                              **P.item(P.AI_GUESS)})
                    inferred.append(r)
    return {"query": q, "interpreted": {"terms": parsed["terms"], "types": sorted(parsed["types"]),
                                        "since": S.iso(parsed["since"]), "until": S.iso(parsed["until"]),
                                        "project": parsed.get("project_scope")},
            "results": stored, "ai_inferred": inferred[:20], "ai_provider": provider}


# ------------------------------------------------------------------ versions & comparison
@router.get("/documents/{doc_id}/versions")
def versions(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db, Document, doc_id, user.id)
    out = []
    labels = {"auto": "Auto-saved", "checkpoint": "Checkpoint", "before_restore": "Before restore", "restore": "Restored"}
    if d.source == "builtin":
        for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id).order_by(DocumentVersion.created_at.desc())):
            out.append({"key": f"v{v.id}", "label": labels.get(v.reason, v.reason), "reason": v.reason, "created_at": S.iso(v.created_at),
                        "words": len(v.content_text.split())})
    else:
        for sn in db.scalars(select(ExternalDocumentSnapshot).where(ExternalDocumentSnapshot.document_id == d.id).order_by(ExternalDocumentSnapshot.captured_at.desc())):
            out.append({"key": f"s{sn.id}", "label": "Checkpoint snapshot" if sn.checkpoint_id else "Read snapshot", "reason": "snapshot",
                        "created_at": S.iso(sn.captured_at), "words": len(sn.text.split())})
    return {"versions": out, "read_only": d.source != "builtin"}


def _text_for(db: Session, d: Document, key: str) -> tuple[str, str]:
    if key == "current":
        return d.content_text or "", "Current text"
    if key.startswith("v"):
        v = db.get(DocumentVersion, int(key[1:]))
        if v and v.document_id == d.id:
            return v.content_text, f"Version {S.iso(v.created_at)}"
    if key.startswith("s"):
        sn = db.get(ExternalDocumentSnapshot, int(key[1:]))
        if sn and sn.document_id == d.id:
            return sn.text, f"Snapshot {S.iso(sn.captured_at)}"
    if key.startswith("cp"):
        sn = db.scalar(select(ExternalDocumentSnapshot).where(ExternalDocumentSnapshot.checkpoint_id == int(key[2:])))
        if sn and sn.document_id == d.id:
            return sn.text, "Checkpoint snapshot"
    raise HTTPException(404, f"Version {key} not found")


@router.get("/documents/{doc_id}/compare")
def compare(doc_id: int, a: str, b: str = "current", user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db, Document, doc_id, user.id)
    at, al = _text_for(db, d, a)
    bt, bl = _text_for(db, d, b)
    import difflib
    sm = difflib.SequenceMatcher(a=at.split(), b=bt.split(), autojunk=False)
    added = sum(j2 - j1 for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("insert", "replace"))
    removed = sum(i2 - i1 for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("delete", "replace"))
    return {"a_text": at, "b_text": bt, "a_label": al, "b_label": bl, "words_added": added, "words_removed": removed,
            "read_only": d.source != "builtin"}


@router.post("/documents/{doc_id}/versions/{version_id}/restore")
def restore_version(doc_id: int, version_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db, Document, doc_id, user.id)
    if d.source != "builtin":
        raise HTTPException(409, "Re-Focus AI never writes into Google Docs or Word. Copy the older text instead.")
    v = db.get(DocumentVersion, version_id)
    if not v or v.document_id != d.id:
        raise HTTPException(404, "Version not found")
    backup = snapshot_version(db, d, "before_restore")
    d.content_json, d.content_text = v.content_json, v.content_text
    snapshot_version(db, d, "restore")
    db.commit()
    return {"document": S.document(d, full=True), "backup_version_id": backup.id}


# ------------------------------------------------------------------ sync
@router.get("/sync/status")
def sync_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A cheap fingerprint of the user's server-side data; clients refetch when it changes."""
    parts = []
    for model in (Project, Document, Checkpoint, UnfinishedThought, UserNote, Reference, Task, AISuggestion):
        col = getattr(model, "updated_at", None) or model.created_at
        cnt, mx = db.execute(select(func.count(), func.max(col)).where(model.user_id == user.id)).one()
        parts.append(f"{model.__tablename__}:{cnt}:{mx}")
    prefs, priv = ensure_settings(db, user)
    parts.append(f"prefs:{prefs.updated_at}:{priv.updated_at}")
    cnt, mx = db.execute(select(func.count(), func.max(ActivityEvent.created_at)).where(ActivityEvent.user_id == user.id)).one()
    parts.append(f"activity:{cnt}:{mx}")
    return {"version": hashlib.sha1("|".join(parts).encode()).hexdigest()[:16], "server_time": utcnow().isoformat()}
