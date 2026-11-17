"""JSON shapes returned by the API, each tagged with provenance where relevant."""
from __future__ import annotations

from . import provenance as P
from .models import (ActivityEvent, BrowserTab, Checkpoint, Document, FutureSelfQuestion, Project, Reference, Task,
                     UnfinishedThought, UserNote, aware)


def iso(dt):
    dt = aware(dt)
    return dt.isoformat() if dt else None


def project(p: Project, pinned: bool = False) -> dict:
    return {"id": p.id, "name": p.name, "category": p.category, "description": p.description,
            "goal": p.goal, "goal_provenance": P.LABELS[P.SAVED_BY_YOU] if p.goal else None,
            "pinned": pinned, "last_active_at": iso(p.last_active_at), "created_at": iso(p.created_at), "updated_at": iso(p.updated_at)}


def document(d: Document, full: bool = False) -> dict:
    out = {"id": d.id, "project_id": d.project_id, "title": d.title, "source": d.source,
           "read_only": d.source != "builtin", "external_url": d.external_url, "cursor_pos": d.cursor_pos,
           "updated_at": iso(d.updated_at), "word_count": len((d.content_text or "").split())}
    if full:
        out["content_json"] = d.content_json
        out["content_text"] = d.content_text
    return out


def position(pos: dict | None) -> dict | None:
    if not pos:
        return None
    src = pos.get("source", "cursor")
    kind = P.AI_GUESS if src == "ai_guess" else P.SAVED_BY_YOU
    return {**pos, **P.item(kind)}


def thought(t: UnfinishedThought, pinned: bool = False) -> dict:
    return {"id": t.id, "project_id": t.project_id, "checkpoint_id": t.checkpoint_id, "document_id": t.document_id,
            "thinking": t.thinking, "missing": t.missing, "next_plan": t.next_plan, "position": position(t.position),
            "reference_ids": t.reference_ids or [], "source_urls": t.source_urls or [], "origin": t.origin,
            "completed": t.completed, "pinned": pinned, "created_at": iso(t.created_at), "updated_at": iso(t.updated_at),
            **P.item(P.SAVED_BY_YOU)}


def future_self(q: FutureSelfQuestion | None) -> dict | None:
    if not q:
        return None
    return {"id": q.id, "question": q.question, "question_edited": q.question_edited, "answer": q.answer,
            "skipped": q.skipped, "generated_by": q.generated_by,
            "question_provenance": P.LABELS[P.SAVED_BY_YOU] if q.question_edited else P.LABELS[P.AI_SUGGESTION],
            "answer_provenance": P.LABELS[P.SAVED_BY_YOU]}


def checkpoint(c: Checkpoint, index: int | None = None, total: int | None = None) -> dict:
    return {"id": c.id, "project_id": c.project_id, "document_id": c.document_id, "document_version_id": c.document_version_id,
            "label": c.label, "goal": c.goal, "position": position(c.position), "included": c.included or {},
            "created_at": iso(c.created_at), "break_started_at": iso(c.break_started_at), "resumed_at": iso(c.resumed_at),
            "index": index, "total": total}


def note(n: UserNote, pinned: bool = False) -> dict:
    return {"id": n.id, "project_id": n.project_id, "checkpoint_id": n.checkpoint_id, "title": n.title, "body": n.body,
            "pinned": pinned, "updated_at": iso(n.updated_at), **P.item(P.SAVED_BY_YOU)}


def reference(r: Reference, pinned: bool = False) -> dict:
    return {"id": r.id, "project_id": r.project_id, "title": r.title, "url": r.url, "authors": r.authors, "year": r.year,
            "why_saved": r.why_saved, "why_saved_provenance": P.LABELS[P.SAVED_BY_YOU],
            "ai_relevance": r.ai_relevance, "ai_relevance_provenance": P.LABELS[P.AI_GUESS] if r.ai_relevance else None,
            "thought_ids": r.thought_ids or [], "checkpoint_ids": r.checkpoint_ids or [], "pinned": pinned,
            "updated_at": iso(r.updated_at)}


def task(t: Task, pinned: bool = False) -> dict:
    prov = P.USER_CONFIRMED if t.origin in ("user", "user_confirmed") else P.AI_SUGGESTION
    return {"id": t.id, "project_id": t.project_id, "checkpoint_id": t.checkpoint_id, "suggestion_id": t.suggestion_id,
            "title": t.title, "status": t.status, "origin": t.origin, "pinned": pinned, "updated_at": iso(t.updated_at),
            **P.item(prov)}


def activity(a: ActivityEvent) -> dict:
    return {"id": a.id, "project_id": a.project_id, "kind": a.kind,
            "title": a.title if not a.excluded else None, "url": a.url if not a.excluded else None,
            "domain": a.domain, "occurred_at": iso(a.occurred_at), "selected": a.selected and not a.excluded,
            "excluded": a.excluded, "status": "excluded" if a.excluded else ("selected" if a.selected else "not selected"),
            **P.item(P.RECORDED_ACTIVITY)}


def tab(t: BrowserTab, excluded: bool) -> dict:
    return {"id": t.id, "tab_id": t.tab_id, "window_id": t.window_id, "device_id": t.device_id, "project_id": t.project_id,
            "title": None if excluded else t.title, "url": None if excluded else t.url, "domain": t.domain,
            "fav_icon_url": None if excluded else t.fav_icon_url, "status": t.status,
            "selected": t.selected and not excluded, "excluded": excluded,
            "content_available": t.content_available and not excluded, "last_seen_at": iso(t.last_seen_at),
            **P.item(P.RECORDED_ACTIVITY)}
