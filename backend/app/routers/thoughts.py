"""Unfinished Thoughts (Feature 8). User wording is stored exactly as typed — never rewritten by AI."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, owned, owned_project
from ..models import Checkpoint, Document, UnfinishedThought, User
from ..schemas import ThoughtIn, ThoughtPatch
from .projects import pinned_ids

router = APIRouter(prefix="/api/thoughts", tags=["thoughts"])


@router.get("")
def list_thoughts(project_id: int | None = None, q: str = "", include_completed: bool = False,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(UnfinishedThought).where(UnfinishedThought.user_id == user.id)
    if project_id:
        stmt = stmt.where(UnfinishedThought.project_id == project_id)
    if not include_completed:
        stmt = stmt.where(UnfinishedThought.completed.is_(False))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(UnfinishedThought.thinking.ilike(like), UnfinishedThought.missing.ilike(like), UnfinishedThought.next_plan.ilike(like)))
    pins = pinned_ids(db, user.id, "thought")
    items = [S.thought(t, t.id in pins) for t in db.scalars(stmt.order_by(UnfinishedThought.created_at.desc()))]
    items.sort(key=lambda t: not t["pinned"])
    return {"thoughts": items}


@router.post("", status_code=201)
def create_thought(body: ThoughtIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_project(db, body.project_id, user.id)
    if body.checkpoint_id:
        owned(db, Checkpoint, body.checkpoint_id, user.id)
    if body.document_id:
        owned(db, Document, body.document_id, user.id)
    if not (body.thinking.strip() or body.missing.strip() or body.next_plan.strip()):
        raise HTTPException(422, "Write at least one field")
    data = body.model_dump()
    data["position"] = body.position.model_dump() if body.position else None
    t = UnfinishedThought(user_id=user.id, **data)
    db.add(t)
    db.commit()
    return S.thought(t)


@router.get("/{thought_id}")
def get_thought(thought_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, UnfinishedThought, thought_id, user.id)
    ids = list(db.scalars(select(UnfinishedThought.id).where(UnfinishedThought.user_id == user.id,
                                                             UnfinishedThought.project_id == t.project_id).order_by(UnfinishedThought.created_at, UnfinishedThought.id)))
    i = ids.index(t.id)
    return {**S.thought(t, t.id in pinned_ids(db, user.id, "thought")),
            "previous_id": ids[i - 1] if i > 0 else None, "next_id": ids[i + 1] if i + 1 < len(ids) else None,
            "position_in_list": i + 1, "total": len(ids)}


@router.patch("/{thought_id}")
def update_thought(thought_id: int, body: ThoughtPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = owned(db, UnfinishedThought, thought_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if data.get("checkpoint_id"):
        owned(db, Checkpoint, data["checkpoint_id"], user.id)
    if "position" in data:
        data["position"] = body.position.model_dump() if body.position else None
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    return S.thought(t)


@router.delete("/{thought_id}", status_code=204)
def delete_thought(thought_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, UnfinishedThought, thought_id, user.id))
    db.commit()
