"""AI features built on the approved context: resume suggestions, Why? clues, feedback."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import provenance as P
from ..models import AISuggestion, Checkpoint, SuggestionEvidence, SuggestionFeedback, Task, aware
from .context import TYPE_LABELS, AIContext, build_context
from .provider import Proposal, call_with_fallback


def _store(db: Session, user_id: int, project_id: int, checkpoint_id: int | None, kind: str, prop: Proposal,
           ctx: AIContext, provider: str) -> AISuggestion:
    s = AISuggestion(user_id=user_id, project_id=project_id, checkpoint_id=checkpoint_id, kind=kind, text=prop.text,
                     provider=provider, context_incomplete=prop.context_incomplete)
    known = ctx.by_ref()
    for i, c in enumerate(prop.clues):
        e = known[c.ref]
        s.evidence.append(SuggestionEvidence(rank=i, evidence_type=e.type, evidence_ref=e.ref, label=e.label[:500],
                                             explanation=c.explanation, excerpt=e.text[:600], url=e.url, certainty=c.certainty))
    db.add(s)
    return s


def resume_suggestions(db: Session, user_id: int, project_id: int, checkpoint: Checkpoint | None,
                       regenerate: bool = False) -> tuple[AISuggestion, AISuggestion]:
    q = select(AISuggestion).where(AISuggestion.user_id == user_id, AISuggestion.project_id == project_id,
                                   AISuggestion.kind.in_(["context_guess", "next_step"]))
    q = q.where(AISuggestion.checkpoint_id == (checkpoint.id if checkpoint else None)) if checkpoint else q.where(AISuggestion.checkpoint_id.is_(None))
    existing: dict[str, AISuggestion] = {}
    for sug in db.scalars(q.order_by(AISuggestion.id.desc())):
        # A rejected AI text is never reused, unless the user replaced it with their own step.
        if sug.kind not in existing and (sug.status != "rejected" or sug.user_text):
            existing[sug.kind] = sug
    if not regenerate and "context_guess" in existing and "next_step" in existing:
        return existing["context_guess"], existing["next_step"]
    ctx = build_context(db, user_id, project_id, checkpoint)
    proposal, provider = call_with_fallback("resume", ctx)
    cid = checkpoint.id if checkpoint else None
    guess = existing.get("context_guess") if not regenerate else None
    guess = guess or _store(db, user_id, project_id, cid, "context_guess", proposal.context_guess, ctx, provider)
    step = _store(db, user_id, project_id, cid, "next_step", proposal.next_step, ctx, provider)
    db.commit()
    return guess, step


def serialize(s: AISuggestion) -> dict:
    """A suggestion with its provenance. Rejected guesses are never shown as verified."""
    if s.user_text or s.status == "accepted":
        prov = P.USER_CONFIRMED
    else:
        prov = P.AI_GUESS if s.kind in ("context_guess", "position_guess") else P.AI_SUGGESTION
    clues = [{"rank": e.rank + 1, "type": e.evidence_type, "type_label": TYPE_LABELS.get(e.evidence_type, e.evidence_type),
              "ref": e.evidence_ref, "label": e.label, "explanation": e.explanation, "excerpt": e.excerpt, "url": e.url,
              "certainty": e.certainty} for e in s.evidence]
    return {
        "id": s.id, "kind": s.kind, "checkpoint_id": s.checkpoint_id, "status": s.status,
        "ai_text": None if s.status == "rejected" else s.text,  # rejected guesses are not shown as information
        "user_text": s.user_text,
        "display_text": s.user_text or (None if s.status == "rejected" else s.text),
        "provider": s.provider, "provider_label": "Placeholder AI (no API key)" if s.provider == "placeholder" else "OpenAI",
        "context_incomplete": s.context_incomplete,
        "clue_count": len(clues), "clue_heading": f"Based on {len(clues)} clue{'s' if len(clues) != 1 else ''}",
        "clues": clues,
        **P.item(prov),
        "created_at": aware(s.created_at).isoformat(),
    }


def give_feedback(db: Session, user_id: int, s: AISuggestion, verdict: str, correction: str, make_task: bool) -> AISuggestion:
    """Accept / Partly / Reject. A correction becomes the user's own, User Confirmed step."""
    correction = (correction or "").strip()
    if verdict == "partly" and not correction:
        raise ValueError("Please say what is needed instead.")
    db.add(SuggestionFeedback(user_id=user_id, suggestion_id=s.id, verdict=verdict, correction=correction))
    s.status = {"accept": "accepted", "partly": "partly", "reject": "rejected"}[verdict]
    s.user_text = correction or None
    if make_task and s.kind == "next_step":
        title = s.user_text or (s.text if verdict == "accept" else None)
        if title:
            db.add(Task(user_id=user_id, project_id=s.project_id, checkpoint_id=s.checkpoint_id, suggestion_id=s.id,
                        title=title, origin="user_confirmed" if s.user_text else "ai_suggestion"))
    db.commit()
    return s


def future_self_question(db: Session, user_id: int, project_id: int, checkpoint: Checkpoint | None, thought: dict | None,
                         position_text: str = "") -> tuple[str, str]:
    ctx = build_context(db, user_id, project_id, checkpoint)
    if position_text and not ctx.position_text:
        ctx.position_text = position_text
    return call_with_fallback("future_self_question", ctx, thought)


def research_connections(db: Session, user_id: int, project_id: int) -> dict:
    ctx = build_context(db, user_id, project_id)
    conns, provider = call_with_fallback("connections", ctx)
    known = ctx.by_ref()
    for c in conns:
        c["evidence"] = [{"ref": r, "type": known[r].type, "type_label": TYPE_LABELS[known[r].type], "label": known[r].label,
                          "url": known[r].url, "excerpt": known[r].text[:300]} for r in c["refs"] if r in known]
        c.update(P.item(P.AI_SUGGESTION))
    return {"provider": provider, "connections": conns, "evidence_considered": len(ctx.evidence)}
