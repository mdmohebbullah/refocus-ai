"""Resume Workspace (10), Why? (11), Help Levels (12), Corrections (13), Transparency (14)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import provenance as P
from .. import serializers as S
from ..ai import service as ai
from ..db import get_db
from ..deps import current_user, ensure_settings, owned, owned_project
from ..models import (AISuggestion, Checkpoint, Document, FutureSelfQuestion, PinnedItem, Reference, SourceSelection, Task,
                      UnfinishedThought, User, UserNote, utcnow)
from ..schemas import FeedbackIn
from ..timekeeping import time_status

router = APIRouter(prefix="/api", tags=["resume"])


def pinned_items(db: Session, user_id: int, project_id: int) -> list[dict]:
    out = []
    loaders = {"thought": (UnfinishedThought, S.thought), "note": (UserNote, S.note), "reference": (Reference, S.reference),
               "task": (Task, S.task)}
    for pin in db.scalars(select(PinnedItem).where(PinnedItem.user_id == user_id).order_by(PinnedItem.created_at.desc())):
        if pin.item_type == "goal":
            from ..models import Project
            p = db.get(Project, pin.item_id)
            if p and p.id == project_id and p.goal:
                out.append({"item_type": "goal", "item": {"id": p.id, "text": p.goal, **P.item(P.SAVED_BY_YOU)}})
            continue
        if pin.item_type not in loaders:
            continue
        model, ser = loaders[pin.item_type]
        obj = db.get(model, pin.item_id)
        if obj and obj.user_id == user_id and getattr(obj, "project_id", None) == project_id:
            out.append({"item_type": pin.item_type, "item": ser(obj, True)})
    return out


def open_link(doc: Document | None, position: dict | None) -> str | None:
    if not doc or not doc.external_url:
        return None
    heading = (position or {}).get("heading_id")
    if doc.source == "google_docs" and heading:
        return f"{doc.external_url.split('#')[0]}#heading={heading}"
    return doc.external_url


@router.get("/projects/{project_id}/resume")
def resume_card(project_id: int, checkpoint_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_project(db, project_id, user.id)
    prefs, _ = ensure_settings(db, user)
    ids = list(db.scalars(select(Checkpoint.id).where(Checkpoint.project_id == project.id, Checkpoint.user_id == user.id).order_by(Checkpoint.id)))
    if checkpoint_id:
        cp = owned(db, Checkpoint, checkpoint_id, user.id)
        if cp.project_id != project.id:
            raise HTTPException(404, "Checkpoint not in this project")
    else:
        cp = db.get(Checkpoint, ids[-1]) if ids else None

    time = time_status(db, user.id, project, prefs)
    doc = db.get(Document, cp.document_id) if cp and cp.document_id else None
    if doc is None:
        doc = db.scalar(select(Document).where(Document.project_id == project.id).order_by(Document.updated_at.desc()))

    goal_text = (cp.goal if cp and cp.goal else project.goal) or ""
    facts = {
        "goal": ({"text": goal_text, **P.item(P.SAVED_BY_YOU)} if goal_text else None),
        "position": S.position(cp.position) if cp else None,
        "thoughts": [], "future_self": None, "sources": [],
    }
    if cp:
        facts["thoughts"] = [S.thought(t) for t in db.scalars(select(UnfinishedThought).where(UnfinishedThought.checkpoint_id == cp.id)
                                                                 .order_by(UnfinishedThought.created_at.desc()))]
        facts["future_self"] = S.future_self(db.scalar(select(FutureSelfQuestion).where(FutureSelfQuestion.checkpoint_id == cp.id)))
        for s in db.scalars(select(SourceSelection).where(SourceSelection.checkpoint_id == cp.id)):
            kind = P.SAVED_BY_YOU if s.kind == "reference" else P.RECORDED_ACTIVITY
            facts["sources"].append({"kind": s.kind, "ref_id": s.ref_id, "title": s.title, "url": s.url, **P.item(kind)})
    else:
        facts["thoughts"] = [S.thought(t) for t in db.scalars(select(UnfinishedThought).where(
            UnfinishedThought.project_id == project.id, UnfinishedThought.completed.is_(False)).order_by(UnfinishedThought.created_at.desc()).limit(3))]

    guess, step = ai.resume_suggestions(db, user.id, project.id, cp)
    tasks = db.scalars(select(Task).where(Task.project_id == project.id, Task.user_id == user.id, Task.status == "open")).all()
    incomplete_reasons = []
    if not cp:
        incomplete_reasons.append("No checkpoint was saved, so this card uses only your project data.")
    if cp and not cp.position:
        incomplete_reasons.append("No writing position was saved.")
    if not facts["thoughts"]:
        incomplete_reasons.append("No unfinished thought was saved.")

    return {
        "project": S.project(project),
        "checkpoint": S.checkpoint(cp, ids.index(cp.id) + 1, len(ids)) if cp else None,
        "timeline": {"index": ids.index(cp.id) + 1 if cp else 0, "total": len(ids),
                     "older_id": ids[ids.index(cp.id) - 1] if cp and ids.index(cp.id) > 0 else None,
                     "newer_id": ids[ids.index(cp.id) + 1] if cp and ids.index(cp.id) + 1 < len(ids) else None},
        "document": {**S.document(doc), "open_url": open_link(doc, cp.position if cp else None)} if doc else None,
        "time": time,
        "facts": facts,
        "ai": {"context_guess": ai.serialize(guess), "next_step": ai.serialize(step)},
        "context_incomplete": bool(incomplete_reasons) or guess.context_incomplete or step.context_incomplete,
        "incomplete_reasons": incomplete_reasons,
        "tasks": [S.task(t) for t in tasks],
        "pinned": pinned_items(db, user.id, project.id),
    }


@router.post("/projects/{project_id}/resume/regenerate")
def regenerate(project_id: int, checkpoint_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    cp = owned(db, Checkpoint, checkpoint_id, user.id) if checkpoint_id else None
    guess, step = ai.resume_suggestions(db, user.id, project_id, cp, regenerate=True)
    return {"context_guess": ai.serialize(guess), "next_step": ai.serialize(step)}


@router.post("/checkpoints/{checkpoint_id}/resume-writing")
def resume_writing(checkpoint_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tap Resume Writing: returns where to put the cursor (built-in) or what to open (Google Docs / Word)."""
    cp = owned(db, Checkpoint, checkpoint_id, user.id)
    cp.resumed_at = utcnow()
    db.commit()
    doc = db.get(Document, cp.document_id) if cp.document_id else None
    pos = cp.position or {}
    if doc is None:
        return {"mode": "none", "message": "This checkpoint has no document."}
    if doc.source == "builtin":
        return {"mode": "editor", "document_id": doc.id, "cursor": pos.get("cursor", doc.cursor_pos),
                "highlight_text": pos.get("paragraph_text", ""), "position": S.position(pos)}
    return {"mode": "external", "document_id": doc.id, "source": doc.source, "open_url": open_link(doc, pos),
            "show_paragraph": pos.get("paragraph_text", ""), "position": S.position(pos),
            "instruction": "Re-Focus AI can't move the cursor inside Google Docs or Word. Look for this paragraph after the document opens."}


@router.get("/suggestions/{suggestion_id}")
def get_suggestion(suggestion_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ai.serialize(owned(db, AISuggestion, suggestion_id, user.id))


@router.post("/suggestions/{suggestion_id}/feedback")
def feedback(suggestion_id: int, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = owned(db, AISuggestion, suggestion_id, user.id)
    try:
        ai.give_feedback(db, user.id, s, body.verdict, body.correction, body.make_task)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return ai.serialize(s)


@router.get("/projects/{project_id}/suggestions")
def list_suggestions(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    items = db.scalars(select(AISuggestion).where(AISuggestion.project_id == project_id, AISuggestion.user_id == user.id)
                       .order_by(AISuggestion.id.desc()).limit(50))
    return {"suggestions": [ai.serialize(s) for s in items]}
