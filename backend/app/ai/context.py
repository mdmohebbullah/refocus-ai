"""Builds the AI context from APPROVED evidence only.

This is the single gate between stored data and any AI provider. Anything excluded here
can never appear in a prompt, a suggestion, or a Why? clue:

* browser tabs/activity the user deselected, or that match an excluded/sensitive domain
* all browser data while Private Mode is on, or while activity collection is off
* items the user unticked in the Pause checklist for this checkpoint
* AI-generated text (AI never cites AI as evidence)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (ActivityEvent, BrowserTab, Checkpoint, FutureSelfQuestion, Project, Reference,
                      SourceSelection, UnfinishedThought, User, UserNote, aware)
from ..privacy import is_excluded
from ..deps import ensure_settings

EVIDENCE_TYPES = ("thought", "note", "goal", "activity", "source", "checkpoint")
TYPE_LABELS = {
    "thought": "Saved unfinished thought",
    "note": "Your note",
    "goal": "Your stated goal",
    "activity": "Selected browser activity",
    "source": "Source",
    "checkpoint": "Previous checkpoint",
}


@dataclass
class Evidence:
    ref: str            # stable id, e.g. "thought:12"
    type: str           # one of EVIDENCE_TYPES
    label: str
    text: str
    url: str | None = None
    at: str | None = None


@dataclass
class AIContext:
    project_id: int
    project_name: str
    checkpoint_id: int | None
    position_text: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    excluded_count: int = 0

    def by_ref(self) -> dict[str, Evidence]:
        return {e.ref: e for e in self.evidence}

    def payload(self) -> dict:
        """Exactly what is sent to an AI provider."""
        return {
            "project": self.project_name,
            "writing_position": self.position_text,
            "evidence": [{"id": e.ref, "type": e.type, "label": e.label, "text": e.text[:1200], "url": e.url}
                         for e in self.evidence],
        }

    def as_dict(self) -> dict:
        return {**self.payload(), "excluded_count": self.excluded_count, "evidence_full": [asdict(e) for e in self.evidence]}


def _included(checkpoint: Checkpoint | None, key: str) -> set[int] | None:
    if checkpoint is None or not checkpoint.included or key not in checkpoint.included:
        return None
    return {int(x) for x in checkpoint.included.get(key) or []}


def build_context(db: Session, user_id: int, project_id: int, checkpoint: Checkpoint | None = None) -> AIContext:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user_id:
        raise ValueError("project not found")
    _, priv = ensure_settings(db, db.get(User, user_id))

    ctx = AIContext(project_id=project.id, project_name=project.name, checkpoint_id=checkpoint.id if checkpoint else None)
    if checkpoint and checkpoint.position:
        ctx.position_text = (checkpoint.position or {}).get("paragraph_text", "") or ""

    # 3. goals ---------------------------------------------------------------
    if project.goal.strip():
        ctx.evidence.append(Evidence("goal:project", "goal", "Project goal", project.goal.strip()))
    if checkpoint and checkpoint.goal.strip() and checkpoint.goal.strip() != project.goal.strip():
        ctx.evidence.append(Evidence(f"goal:checkpoint{checkpoint.id}", "goal", "Goal saved at pause", checkpoint.goal.strip()))

    # 1. unfinished thoughts (+ future-self answers, also user-written) ----------
    inc_thoughts = _included(checkpoint, "thoughts")
    thoughts = db.scalars(select(UnfinishedThought).where(UnfinishedThought.user_id == user_id,
                                                          UnfinishedThought.project_id == project_id,
                                                          UnfinishedThought.completed.is_(False))
                          .order_by(UnfinishedThought.updated_at.desc()).limit(20)).all()
    for t in thoughts:
        if inc_thoughts is not None and t.id not in inc_thoughts and t.checkpoint_id != (checkpoint.id if checkpoint else None):
            ctx.excluded_count += 1
            continue
        parts = [p for p in [t.thinking and f"Thinking: {t.thinking}", t.missing and f"Missing: {t.missing}",
                             t.next_plan and f"Planned next: {t.next_plan}"] if p]
        if parts:
            ctx.evidence.append(Evidence(f"thought:{t.id}", "thought", "Your unfinished thought", " | ".join(parts),
                                         at=aware(t.updated_at).isoformat()))
    if checkpoint:
        fsq = db.scalar(select(FutureSelfQuestion).where(FutureSelfQuestion.checkpoint_id == checkpoint.id))
        if fsq and fsq.answer.strip() and not fsq.skipped:
            ctx.evidence.append(Evidence(f"answer:{fsq.id}", "thought", "Your answer to your future self",
                                         f"Q: {fsq.question} A: {fsq.answer}"))

    # 2. notes -----------------------------------------------------------------
    inc_notes = _included(checkpoint, "notes")
    for n in db.scalars(select(UserNote).where(UserNote.user_id == user_id, UserNote.project_id == project_id)
                        .order_by(UserNote.updated_at.desc()).limit(20)):
        if inc_notes is not None and n.id not in inc_notes:
            ctx.excluded_count += 1
            continue
        ctx.evidence.append(Evidence(f"note:{n.id}", "note", n.title or "Your note", n.body))

    # 5. sources: references (user-written fields only) ----------------------
    inc_refs = _included(checkpoint, "references")
    for r in db.scalars(select(Reference).where(Reference.user_id == user_id, Reference.project_id == project_id)
                        .order_by(Reference.updated_at.desc()).limit(30)):
        if inc_refs is not None and r.id not in inc_refs:
            ctx.excluded_count += 1
            continue
        if r.url and is_excluded(r.url, priv):
            ctx.excluded_count += 1
            continue
        meta = ", ".join(x for x in [r.authors, str(r.year) if r.year else ""] if x)
        text = r.title + (f" ({meta})" if meta else "") + (f". Why you saved it: {r.why_saved}" if r.why_saved else "")
        ctx.evidence.append(Evidence(f"reference:{r.id}", "source", r.title, text, url=r.url))

    browser_allowed = priv.activity_collection and not priv.private_mode

    # 5. sources: selected tabs ------------------------------------------------
    inc_tabs = _included(checkpoint, "tabs")
    if checkpoint is not None and inc_tabs is not None:
        # Use the tab snapshot frozen at pause time.
        for s in db.scalars(select(SourceSelection).where(SourceSelection.checkpoint_id == checkpoint.id,
                                                          SourceSelection.kind == "tab")):
            if not browser_allowed or is_excluded(s.url, priv):
                ctx.excluded_count += 1
                continue
            ctx.evidence.append(Evidence(f"tab:{s.ref_id}", "source", s.title or s.url or "Tab", s.title, url=s.url))
    elif browser_allowed:
        for tab in db.scalars(select(BrowserTab).where(BrowserTab.user_id == user_id, BrowserTab.selected.is_(True))):
            if tab.project_id not in (None, project_id) or is_excluded(tab.url, priv):
                ctx.excluded_count += 1
                continue
            text = tab.title + (f". Page excerpt: {tab.content_excerpt[:600]}" if tab.content_excerpt else "")
            ctx.evidence.append(Evidence(f"tab:{tab.id}", "source", tab.title or tab.url, text, url=tab.url))

    # 4. selected browser activity -------------------------------------------
    inc_act = _included(checkpoint, "activity")
    if browser_allowed:
        q = select(ActivityEvent).where(ActivityEvent.user_id == user_id, ActivityEvent.selected.is_(True),
                                        ActivityEvent.excluded.is_(False))
        q = q.where((ActivityEvent.project_id == project_id) | (ActivityEvent.project_id.is_(None)))
        for a in db.scalars(q.order_by(ActivityEvent.occurred_at.desc()).limit(40)):
            if inc_act is not None and a.id not in inc_act:
                ctx.excluded_count += 1
                continue
            if is_excluded(a.url, priv):
                ctx.excluded_count += 1
                continue
            ctx.evidence.append(Evidence(f"activity:{a.id}", "activity", a.title or a.domain or "Visited page",
                                         f"Visited '{a.title}' at {aware(a.occurred_at).isoformat()}", url=a.url,
                                         at=aware(a.occurred_at).isoformat()))
    else:
        ctx.excluded_count += 1

    # 6. previous checkpoints -------------------------------------------------
    q = select(Checkpoint).where(Checkpoint.user_id == user_id, Checkpoint.project_id == project_id)
    if checkpoint:
        q = q.where(Checkpoint.id < checkpoint.id)
    for c in db.scalars(q.order_by(Checkpoint.id.desc()).limit(3)):
        pos = (c.position or {}).get("paragraph_text", "")
        text = "; ".join(x for x in [c.label, c.goal and f"Goal: {c.goal}", pos and f"Stopped at: {pos}"] if x)
        if text:
            ctx.evidence.append(Evidence(f"checkpoint:{c.id}", "checkpoint", c.label or f"Checkpoint {c.id}", text,
                                         at=aware(c.created_at).isoformat()))
    return ctx
