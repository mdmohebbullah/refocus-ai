"""Notes, References & Smart Bookmarks (20), Research Connections (21), Tasks & Pinning (22)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..ai import service as ai
from ..db import get_db
from ..deps import current_user, owned, owned_project
from ..models import (AISuggestion, Checkpoint, PinnedItem, Project, Reference, Task, UnfinishedThought, User, UserNote)
from ..schemas import NoteIn, NotePatch, PinIn, ReferenceIn, ReferencePatch, TaskIn, TaskPatch
from .projects import pinned_ids

router = APIRouter(prefix="/api", tags=["research"])


# ------------------------------------------------------------------ notes
@router.get("/notes")
def list_notes(project_id: int, q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    stmt = select(UserNote).where(UserNote.user_id == user.id, UserNote.project_id == project_id)
    if q:
        stmt = stmt.where(or_(UserNote.title.ilike(f"%{q}%"), UserNote.body.ilike(f"%{q}%")))
    pins = pinned_ids(db, user.id, "note")
    out = [S.note(n, n.id in pins) for n in db.scalars(stmt.order_by(UserNote.updated_at.desc()))]
    out.sort(key=lambda n: not n["pinned"])
    return {"notes": out}


@router.post("/notes", status_code=201)
def create_note(body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, body.project_id, user.id)
    if body.checkpoint_id:
        owned(db, Checkpoint, body.checkpoint_id, user.id)
    n = UserNote(user_id=user.id, **body.model_dump())
    db.add(n)
    db.commit()
    return S.note(n)


@router.patch("/notes/{note_id}")
def update_note(note_id: int, body: NotePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = owned(db, UserNote, note_id, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(n, k, v)
    db.commit()
    return S.note(n)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, UserNote, note_id, user.id))
    db.commit()


# ------------------------------------------------------------------ references
def _check_links(db, user_id, thought_ids, checkpoint_ids):
    for t in thought_ids or []:
        owned(db, UnfinishedThought, t, user_id)
    for c in checkpoint_ids or []:
        owned(db, Checkpoint, c, user_id)


@router.get("/references")
def list_references(project_id: int, q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    stmt = select(Reference).where(Reference.user_id == user.id, Reference.project_id == project_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Reference.title.ilike(like), Reference.authors.ilike(like), Reference.why_saved.ilike(like), Reference.url.ilike(like)))
    pins = pinned_ids(db, user.id, "reference")
    out = [S.reference(r, r.id in pins) for r in db.scalars(stmt.order_by(Reference.updated_at.desc()))]
    out.sort(key=lambda r: not r["pinned"])
    return {"references": out}


@router.post("/references", status_code=201)
def create_reference(body: ReferenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, body.project_id, user.id)
    _check_links(db, user.id, body.thought_ids, body.checkpoint_ids)
    if body.year is not None and not (1000 <= body.year <= 2100):
        raise HTTPException(422, "Publication year looks wrong")
    r = Reference(user_id=user.id, **body.model_dump())
    db.add(r)
    db.commit()
    return S.reference(r)


@router.patch("/references/{ref_id}")
def update_reference(ref_id: int, body: ReferencePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = owned(db, Reference, ref_id, user.id)
    data = body.model_dump(exclude_unset=True)
    _check_links(db, user.id, data.get("thought_ids"), data.get("checkpoint_ids"))
    for k, v in data.items():
        setattr(r, k, v)
    db.commit()
    return S.reference(r)


@router.delete("/references/{ref_id}", status_code=204)
def delete_reference(ref_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Reference, ref_id, user.id))
    db.commit()


@router.post("/projects/{project_id}/connect-research")
def connect_research(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Connect My Research — uses only approved, accessible items; every connection cites them."""
    owned_project(db, project_id, user.id)
    return ai.research_connections(db, user.id, project_id)


# ------------------------------------------------------------------ tasks
@router.get("/tasks")
def list_tasks(project_id: int, status: str = "open", user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, project_id, user.id)
    stmt = select(Task).where(Task.user_id == user.id, Task.project_id == project_id)
    if status != "all":
        stmt = stmt.where(Task.status == status)
    pins = pinned_ids(db, user.id, "task")
    return {"tasks": [S.task(t, t.id in pins) for t in db.scalars(stmt.order_by(Task.created_at.desc()))]}


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, body.project_id, user.id)
    origin = "user"
    if body.suggestion_id:
        s = owned(db, AISuggestion, body.suggestion_id, user.id)
        origin = "user_confirmed" if s.user_text else "ai_suggestion"
    if body.checkpoint_id:
        owned(db, Checkpoint, body.checkpoint_id, user.id)
    t = Task(user_id=user.id, origin=origin, **body.model_dump())
    db.add(t)
    db.commit()
    return S.task(t)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, Task, task_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] != t.title and t.origin == "ai_suggestion":
        t.origin = "user_confirmed"  # an edited AI task is the user's own wording now
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    return S.task(t)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Task, task_id, user.id))
    db.commit()


# ------------------------------------------------------------------ pins
PIN_MODELS = {"project": Project, "thought": UnfinishedThought, "note": UserNote, "reference": Reference, "task": Task, "goal": Project}


@router.post("/pins", status_code=201)
def pin(body: PinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    obj = owned(db, PIN_MODELS[body.item_type], body.item_id, user.id)
    project_id = obj.id if body.item_type in ("project", "goal") else obj.project_id
    exists = db.scalar(select(PinnedItem).where(PinnedItem.user_id == user.id, PinnedItem.item_type == body.item_type, PinnedItem.item_id == body.item_id))
    if not exists:
        db.add(PinnedItem(user_id=user.id, project_id=project_id, item_type=body.item_type, item_id=body.item_id))
        db.commit()
    return {"pinned": True}


@router.delete("/pins/{item_type}/{item_id}", status_code=204)
def unpin(item_type: str, item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(PinnedItem).where(PinnedItem.user_id == user.id, PinnedItem.item_type == item_type, PinnedItem.item_id == item_id))
    db.commit()


@router.get("/pins")
def list_pins(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .resume import pinned_items
    owned_project(db, project_id, user.id)
    return {"pinned": pinned_items(db, user.id, project_id)}
