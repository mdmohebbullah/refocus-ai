from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..db import get_db
from ..deps import current_user, ensure_settings, owned, owned_project
from ..models import Document, DocumentVersion, PinnedItem, Project, User, aware, utcnow
from ..schemas import DocumentIn, DocumentPatch, ProjectIn, ProjectPatch

router = APIRouter(prefix="/api", tags=["projects"])
CATEGORIES = ["research_paper", "assignment", "dissertation", "literature_review", "general"]
AUTO_VERSION_EVERY = timedelta(minutes=5)


def pinned_ids(db: Session, user_id: int, item_type: str) -> set[int]:
    return set(db.scalars(select(PinnedItem.item_id).where(PinnedItem.user_id == user_id, PinnedItem.item_type == item_type)))


@router.get("/projects")
def list_projects(q: str = "", category: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Project).where(Project.user_id == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Project.name.ilike(like), Project.description.ilike(like), Project.goal.ilike(like)))
    if category:
        stmt = stmt.where(Project.category == category)
    pins = pinned_ids(db, user.id, "project")
    projects = db.scalars(stmt.order_by(Project.updated_at.desc())).all()
    out = [S.project(p, p.id in pins) for p in projects]
    out.sort(key=lambda p: (not p["pinned"],))  # pinned first, otherwise most recent
    return {"projects": out, "categories": CATEGORIES}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    p = Project(user_id=user.id, **body.model_dump())
    db.add(p)
    db.flush()
    db.add(Document(user_id=user.id, project_id=p.id, title="Main draft", content_json=None, content_text=""))
    prefs, _ = ensure_settings(db, user)
    prefs.current_project_id = p.id
    db.commit()
    return S.project(p)


@router.get("/projects/{project_id}")
def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, project_id, user.id)
    docs = db.scalars(select(Document).where(Document.project_id == p.id).order_by(Document.updated_at.desc())).all()
    return {**S.project(p, p.id in pinned_ids(db, user.id, "project")), "documents": [S.document(d) for d in docs]}


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, project_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if data.get("category") and data["category"] not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    for k, v in data.items():
        if v is not None:
            setattr(p, k, v)
    db.commit()
    return S.project(p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, project_id, user.id)
    db.query(PinnedItem).filter(PinnedItem.user_id == user.id, PinnedItem.item_type == "project", PinnedItem.item_id == p.id).delete()
    prefs, _ = ensure_settings(db, user)
    if prefs.current_project_id == p.id:
        prefs.current_project_id = None
    db.delete(p)
    db.commit()


# ------------------------------------------------------------------ documents
@router.post("/projects/{project_id}/documents", status_code=201)
def create_document(project_id: int, body: DocumentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(db, project_id, user.id)
    d = Document(user_id=user.id, project_id=p.id, title=body.title)
    db.add(d)
    db.commit()
    return S.document(d, full=True)


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return S.document(owned(db, Document, doc_id, user.id), full=True)


def snapshot_version(db: Session, d: Document, reason: str) -> DocumentVersion:
    v = DocumentVersion(user_id=d.user_id, document_id=d.id, content_json=d.content_json, content_text=d.content_text or "", reason=reason)
    db.add(v)
    db.flush()
    return v


@router.patch("/documents/{doc_id}")
def update_document(doc_id: int, body: DocumentPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db, Document, doc_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if d.source != "builtin" and ({"content_json", "content_text"} & data.keys()):
        raise HTTPException(409, "Connected Google Docs / Word documents are read-only in Re-Focus AI")
    content_changed = "content_text" in data and data["content_text"] != d.content_text
    for k, v in data.items():
        setattr(d, k, v)
    if content_changed:
        last = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == d.id).order_by(DocumentVersion.created_at.desc()))
        if last is None or utcnow() - aware(last.created_at) >= AUTO_VERSION_EVERY:
            snapshot_version(db, d, "auto")
        d.updated_at = utcnow()
        p = db.get(Project, d.project_id)
        p.updated_at = utcnow()
    db.commit()
    return S.document(d)


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = owned(db, Document, doc_id, user.id)
    db.delete(d)
    db.commit()
