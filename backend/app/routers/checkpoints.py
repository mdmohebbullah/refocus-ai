"""Pause & Checkpoints (Feature 7), Question for Your Future Self (9), Checkpoint Timeline (5B)."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..ai import service as ai
from ..db import get_db
from ..deps import current_user, ensure_settings, owned, owned_project
from ..models import (ActivityEvent, BrowserTab, Checkpoint, Document, DocumentVersion, ExternalDocumentSnapshot,
                      FutureSelfQuestion, Reference, SourceSelection, Task, UnfinishedThought, User, UserNote, WorkSession,
                      utcnow)
from ..privacy import is_excluded
from ..schemas import CheckpointIn, FutureSelfIn
from .projects import snapshot_version

router = APIRouter(prefix="/api", tags=["checkpoints"])


def _external(db: Session, doc: Document):
    from ..integrations import external_docs  # lazy: optional network integrations
    return external_docs


@router.get("/projects/{project_id}/pause-draft")
def pause_draft(project_id: int, document_id: int | None = None, cursor: int | None = None, paragraph_text: str = "",
                paragraph_index: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything Pause Session proposes to save. Nothing is stored until the user saves."""
    project = owned_project(db, project_id, user.id)
    _, priv = ensure_settings(db, user)
    doc = owned(db, Document, document_id, user.id) if document_id else None
    browser_ok = priv.activity_collection and not priv.private_mode

    position = None
    paragraphs = None
    if doc and doc.source == "builtin":
        position = {"cursor": cursor, "paragraph_index": paragraph_index, "paragraph_text": paragraph_text, "source": "cursor"}
    elif doc:
        try:
            snap = _external(db, doc).fresh_snapshot(db, user, doc)
            paragraphs = snap["paragraphs"]
        except Exception as e:  # network / auth problem: user can still save without marking
            paragraphs = {"error": str(e)}

    tabs = []
    if browser_ok:
        for t in db.scalars(select(BrowserTab).where(BrowserTab.user_id == user.id, BrowserTab.selected.is_(True))):
            if t.project_id in (None, project.id) and not is_excluded(t.url, priv):
                tabs.append(S.tab(t, False))
    since = utcnow() - timedelta(minutes=60)
    acts = []
    if browser_ok:
        for a in db.scalars(select(ActivityEvent).where(ActivityEvent.user_id == user.id, ActivityEvent.occurred_at >= since,
                                                       ActivityEvent.selected.is_(True), ActivityEvent.excluded.is_(False))
                            .order_by(ActivityEvent.occurred_at.desc()).limit(30)):
            if a.project_id in (None, project.id) and not is_excluded(a.url, priv):
                acts.append(S.activity(a))
    thoughts = db.scalars(select(UnfinishedThought).where(UnfinishedThought.user_id == user.id, UnfinishedThought.project_id == project.id,
                                                         UnfinishedThought.completed.is_(False)).order_by(UnfinishedThought.updated_at.desc()).limit(10)).all()
    notes = db.scalars(select(UserNote).where(UserNote.project_id == project.id, UserNote.user_id == user.id).order_by(UserNote.updated_at.desc()).limit(10)).all()
    refs = db.scalars(select(Reference).where(Reference.project_id == project.id, Reference.user_id == user.id).order_by(Reference.updated_at.desc()).limit(10)).all()
    tasks = db.scalars(select(Task).where(Task.project_id == project.id, Task.user_id == user.id, Task.status == "open")).all()

    latest = thoughts[0] if thoughts else None
    thought_fields = {"thinking": latest.thinking, "missing": latest.missing, "next_plan": latest.next_plan} if latest else None
    question, provider = ai.future_self_question(db, user.id, project.id, None, thought_fields, paragraph_text)

    links = [{"title": r.title, "url": r.url} for r in refs if r.url] + [{"title": t["title"], "url": t["url"]} for t in tabs if t.get("url")]
    return {
        "project": S.project(project), "document": S.document(doc) if doc else None,
        "position": S.position(position), "external_paragraphs": paragraphs,
        "goal": project.goal,
        "tabs": tabs, "activity": acts,
        "thoughts": [S.thought(t) for t in thoughts], "notes": [S.note(n) for n in notes],
        "references": [S.reference(r) for r in refs], "tasks": [S.task(t) for t in tasks],
        "source_links": links,
        "future_self": {"question": question, "generated_by": provider, "provenance_label": "AI Suggestion"},
        "browser_collection": "on" if browser_ok else ("private mode" if priv.private_mode else "off"),
    }


@router.post("/checkpoints", status_code=201)
def create_checkpoint(body: CheckpointIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_project(db, body.project_id, user.id)
    _, priv = ensure_settings(db, user)
    doc = owned(db, Document, body.document_id, user.id) if body.document_id else None
    inc = body.included

    def keep(model, ids):
        return [i for i in ids if (o := db.get(model, i)) is not None and o.user_id == user.id]

    included = {
        "tabs": keep(BrowserTab, inc.tabs), "activity": keep(ActivityEvent, inc.activity),
        "thoughts": keep(UnfinishedThought, inc.thoughts), "notes": keep(UserNote, inc.notes),
        "references": keep(Reference, inc.references), "tasks": keep(Task, inc.tasks),
        "include_position": inc.include_position, "include_goal": inc.include_goal,
    }
    position = body.position.model_dump() if (body.position and inc.include_position) else None
    c = Checkpoint(user_id=user.id, project_id=project.id, document_id=doc.id if doc else None,
                   label=body.label or f"Paused {utcnow().strftime('%b %d, %H:%M UTC')}",
                   goal=(body.goal or project.goal) if inc.include_goal else "", position=position, included=included,
                   break_started_at=utcnow())
    db.add(c)
    db.flush()
    if body.goal and inc.include_goal and not project.goal:
        project.goal = body.goal

    if doc and doc.source == "builtin":
        if position and position.get("cursor") is not None:
            doc.cursor_pos = position["cursor"]
        c.document_version_id = snapshot_version(db, doc, "checkpoint").id
    elif doc:
        try:
            ext = _external(db, doc)
            snap = ext.store_snapshot(db, user, doc, c.id)
            if inc.include_position and (not position or position.get("source") != "user_marked"):
                guess = ext.guess_position(db, doc, snap)
                c.position = guess
        except Exception as e:
            c.position = position or {"paragraph_text": "", "source": "ai_guess", "note": f"Snapshot failed: {e}"}

    # Freeze the approved sources at pause time.
    for tid in included["tabs"]:
        t = db.get(BrowserTab, tid)
        if t and not is_excluded(t.url, priv):
            db.add(SourceSelection(user_id=user.id, project_id=project.id, checkpoint_id=c.id, kind="tab", ref_id=t.id, title=t.title, url=t.url))
    for aid in included["activity"]:
        a = db.get(ActivityEvent, aid)
        if a and not a.excluded and not is_excluded(a.url, priv):
            db.add(SourceSelection(user_id=user.id, project_id=project.id, checkpoint_id=c.id, kind="activity", ref_id=a.id, title=a.title or "", url=a.url))
    for rid in included["references"]:
        r = db.get(Reference, rid)
        db.add(SourceSelection(user_id=user.id, project_id=project.id, checkpoint_id=c.id, kind="reference", ref_id=r.id, title=r.title, url=r.url))
        r.checkpoint_ids = sorted(set((r.checkpoint_ids or []) + [c.id]))
    for tid in included["thoughts"]:
        t = db.get(UnfinishedThought, tid)
        if t.checkpoint_id is None:
            t.checkpoint_id = c.id
    for tid in included["tasks"]:
        t = db.get(Task, tid)
        if t.checkpoint_id is None:
            t.checkpoint_id = c.id

    if body.new_thought and (body.new_thought.thinking or body.new_thought.missing or body.new_thought.next_plan):
        nt = body.new_thought
        th = UnfinishedThought(user_id=user.id, project_id=project.id, checkpoint_id=c.id, document_id=doc.id if doc else None,
                               thinking=nt.thinking, missing=nt.missing, next_plan=nt.next_plan,
                               position=(nt.position.model_dump() if nt.position else position), reference_ids=nt.reference_ids,
                               source_urls=nt.source_urls, origin=nt.origin)
        db.add(th)
        db.flush()
        c.included = {**c.included, "thoughts": c.included["thoughts"] + [th.id]}

    if body.future_self and body.future_self.question.strip():
        fs = body.future_self
        db.add(FutureSelfQuestion(user_id=user.id, checkpoint_id=c.id, question=fs.question.strip(), question_edited=fs.question_edited,
                                  answer="" if fs.skipped else fs.answer.strip(), skipped=fs.skipped, generated_by=fs.generated_by))

    for sess in db.scalars(select(WorkSession).where(WorkSession.user_id == user.id, WorkSession.project_id == project.id, WorkSession.status == "active")):
        sess.status = "paused"
        sess.ended_at = utcnow()
    db.commit()
    return detail(c, db)


def detail(c: Checkpoint, db: Session) -> dict:
    ids = list(db.scalars(select(Checkpoint.id).where(Checkpoint.project_id == c.project_id, Checkpoint.user_id == c.user_id).order_by(Checkpoint.id)))
    i = ids.index(c.id)
    fs = db.scalar(select(FutureSelfQuestion).where(FutureSelfQuestion.checkpoint_id == c.id))
    sources = db.scalars(select(SourceSelection).where(SourceSelection.checkpoint_id == c.id)).all()
    thoughts = db.scalars(select(UnfinishedThought).where(UnfinishedThought.checkpoint_id == c.id)).all()
    return {**S.checkpoint(c, i + 1, len(ids)),
            "older_id": ids[i - 1] if i > 0 else None, "newer_id": ids[i + 1] if i + 1 < len(ids) else None,
            "future_self": S.future_self(fs),
            "sources": [{"kind": s.kind, "ref_id": s.ref_id, "title": s.title, "url": s.url,
                         "provenance_label": "Saved by You" if s.kind == "reference" else "Recorded Activity"} for s in sources],
            "thoughts": [S.thought(t) for t in thoughts]}


@router.get("/projects/{project_id}/checkpoints")
def list_checkpoints(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    cs = db.scalars(select(Checkpoint).where(Checkpoint.project_id == project_id, Checkpoint.user_id == user.id).order_by(Checkpoint.id)).all()
    return {"checkpoints": [S.checkpoint(c, i + 1, len(cs)) for i, c in enumerate(cs)], "total": len(cs)}


@router.get("/checkpoints/{checkpoint_id}")
def get_checkpoint(checkpoint_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return detail(owned(db, Checkpoint, checkpoint_id, user.id), db)


@router.put("/checkpoints/{checkpoint_id}/future-self")
def save_future_self(checkpoint_id: int, body: FutureSelfIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned(db, Checkpoint, checkpoint_id, user.id)
    fs = db.scalar(select(FutureSelfQuestion).where(FutureSelfQuestion.checkpoint_id == c.id))
    if not fs:
        fs = FutureSelfQuestion(user_id=user.id, checkpoint_id=c.id, question=body.question)
        db.add(fs)
    fs.question, fs.question_edited, fs.skipped = body.question, body.question_edited, body.skipped
    fs.answer = "" if body.skipped else body.answer
    fs.generated_by = body.generated_by
    db.commit()
    return S.future_self(fs)


@router.delete("/checkpoints/{checkpoint_id}", status_code=204)
def delete_checkpoint(checkpoint_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = owned(db, Checkpoint, checkpoint_id, user.id)
    db.delete(c)
    db.commit()


@router.post("/checkpoints/{checkpoint_id}/restore")
def restore_checkpoint(checkpoint_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Non-destructive: the current text is saved as a new version before restoring."""
    c = owned(db, Checkpoint, checkpoint_id, user.id)
    doc = db.get(Document, c.document_id) if c.document_id else None
    if not doc:
        raise HTTPException(404, "This checkpoint has no document")
    if doc.source != "builtin":
        snap = db.scalar(select(ExternalDocumentSnapshot).where(ExternalDocumentSnapshot.checkpoint_id == c.id))
        raise HTTPException(409, {"message": "Re-Focus AI never writes into Google Docs or Word. Copy the older text instead.",
                                  "copy_text": snap.text if snap else ""})
    v = db.get(DocumentVersion, c.document_version_id) if c.document_version_id else None
    if not v:
        raise HTTPException(404, "No saved version for this checkpoint")
    backup = snapshot_version(db, doc, "before_restore")
    doc.content_json, doc.content_text = v.content_json, v.content_text
    if c.position and c.position.get("cursor") is not None:
        doc.cursor_pos = c.position["cursor"]
    snapshot_version(db, doc, "restore")
    db.commit()
    return {"document": S.document(doc, full=True), "backup_version_id": backup.id}
