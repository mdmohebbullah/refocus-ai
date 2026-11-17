"""AI providers.

`OpenAIProvider` calls the OpenAI API with structured JSON output. `PlaceholderProvider`
is deterministic, needs no key, and is used for local development, tests, and as a
fallback when the API fails. Both receive ONLY `AIContext.payload()`.

Every clue a provider returns must cite an evidence id from the context; anything else
is discarded by `validate_clues`, and at most three clues are ever kept.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from ..config import get_settings
from .context import AIContext, Evidence

log = logging.getLogger("refocus.ai")
MAX_CLUES = 3

STOPWORDS = set("""a an the and or but if then else of to in on at for with by from as is are was were be been being this that these
those it its into about over under than so such not no yes do does did i you he she we they my your our their me him her them us
what which who whom why how when where can could should would will just also more most very much many some any each other between
because however while there here up down out off again further once only own same too s t don now study studies paper""".split())


def keywords(text: str, n: int = 8) -> list[str]:
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (text or "").lower()) if w not in STOPWORDS]
    return [w for w, _ in Counter(words).most_common(n)]


def overlap(a: str, b: str) -> int:
    return len(set(keywords(a, 20)) & set(keywords(b, 20)))


def tail_words(text: str, n: int = 8) -> str:
    words = (text or "").strip().split()
    return ("…" if len(words) > n else "") + " ".join(words[-n:])


@dataclass
class Clue:
    ref: str
    explanation: str
    certainty: str = "medium"


@dataclass
class Proposal:
    text: str
    clues: list[Clue] = field(default_factory=list)
    context_incomplete: bool = False


@dataclass
class ResumeProposal:
    context_guess: Proposal
    next_step: Proposal
    provider: str


def validate_clues(ctx: AIContext, clues: list[Clue]) -> list[Clue]:
    """Keep only clues that cite real, approved evidence; never more than three; no duplicates."""
    known = ctx.by_ref()
    out, seen = [], set()
    for c in clues:
        if c.ref in known and c.ref not in seen and c.explanation.strip():
            seen.add(c.ref)
            out.append(Clue(c.ref, c.explanation.strip()[:500], c.certainty if c.certainty in ("low", "medium", "high") else "medium"))
        if len(out) == MAX_CLUES:
            break
    return out


# --------------------------------------------------------------------------- placeholder
class PlaceholderProvider:
    name = "placeholder"

    def _rank(self, ctx: AIContext, focus: str) -> list[Evidence]:
        prio = {"thought": 5, "goal": 4, "source": 3, "note": 3, "checkpoint": 2, "activity": 1}

        def score(e: Evidence):
            return (overlap(focus, e.text) * 3 + prio.get(e.type, 0), e.at or "")
        return sorted(ctx.evidence, key=score, reverse=True)

    def _explain(self, e: Evidence, focus: str) -> Clue:
        shared = sorted(set(keywords(focus, 20)) & set(keywords(e.text, 20)))[:3]
        link = f" It shares the terms {', '.join(repr(s) for s in shared)} with where you stopped." if shared else ""
        base = {
            "thought": "You wrote this yourself before your break.",
            "goal": "This is the goal you saved for this work.",
            "note": "This is one of your notes for this project.",
            "source": "You selected this source for this project.",
            "activity": "You visited this page shortly before your break (selected activity).",
            "checkpoint": "This is where you stopped at an earlier checkpoint.",
        }[e.type]
        certainty = "high" if e.type in ("thought", "goal") else ("medium" if shared else "low")
        return Clue(e.ref, base + link, certainty)

    def resume(self, ctx: AIContext) -> ResumeProposal:
        thoughts = [e for e in ctx.evidence if e.type == "thought" and e.ref.startswith("thought:")]
        goals = [e for e in ctx.evidence if e.type == "goal"]
        focus = ctx.position_text or (thoughts[0].text if thoughts else (goals[0].text if goals else ""))
        ranked = self._rank(ctx, focus)
        incomplete = len(ctx.evidence) < 2

        # Context guess — "what you may have been doing"
        if ctx.position_text:
            guess = f"You may have been finishing the paragraph that ends “{tail_words(ctx.position_text, 10)}”"
            if thoughts:
                guess += f", while working out this idea: {self._field(thoughts[0].text, 'Thinking')}"
            guess += "."
        elif thoughts:
            guess = f"You may have been developing this idea: {self._field(thoughts[0].text, 'Thinking')}."
        elif goals:
            guess = f"You may have been working toward your goal: {goals[0].text}."
        else:
            guess = "Not enough saved context to guess what you were doing."
            incomplete = True

        # Next step — one clear action
        plan = next((self._field(t.text, "Planned next") for t in thoughts if "Planned next:" in t.text), "")
        missing = next((self._field(t.text, "Missing") for t in thoughts if "Missing:" in t.text), "")
        if plan:
            step = f"Start with what you planned: {plan}"
        elif missing:
            step = f"Find what was missing: {missing}"
        elif ctx.position_text:
            step = f"Finish the sentence that ends “{tail_words(ctx.position_text, 8)}”."
        elif goals:
            step = f"Write the next part toward your goal: {goals[0].text}"
        else:
            step = "Re-read your last paragraph and write one next sentence."
            incomplete = True

        clues = validate_clues(ctx, [self._explain(e, focus) for e in ranked[:MAX_CLUES]])
        step_rank = self._rank(ctx, f"{step} {focus}")
        step_clues = validate_clues(ctx, [self._explain(e, step) for e in step_rank[:MAX_CLUES]])
        return ResumeProposal(Proposal(guess, clues, incomplete), Proposal(step, step_clues, incomplete), self.name)

    @staticmethod
    def _field(text: str, name: str) -> str:
        for part in text.split(" | "):
            if part.startswith(name + ":"):
                return part.split(":", 1)[1].strip().rstrip(".!?;, ")
        return text.rstrip(".!?;, ")

    def future_self_question(self, ctx: AIContext, thought: dict | None) -> str:
        thought = thought or {}
        has_tabs = any(e.type in ("source", "activity") for e in ctx.evidence)
        if not thought.get("thinking"):
            if ctx.position_text:
                return f"What were you about to write after “{tail_words(ctx.position_text, 6)}”?"
            return "What were you trying to finish before this break?"
        if not thought.get("missing"):
            return "What information is still missing for this idea?"
        if not thought.get("next_plan"):
            return "What will you do first when you come back?"
        if has_tabs:
            return "Which source will you open first when you return, and why?"
        return "Which problem were you trying to solve in this section?"

    def connections(self, ctx: AIContext) -> list[dict]:
        items = [e for e in ctx.evidence if e.type in ("thought", "note", "source")]
        terms = Counter()
        for e in items:
            terms.update(set(keywords(e.text, 12)))
        out = []
        for term, count in terms.most_common(8):
            if count < 2:
                continue
            refs = [e.ref for e in items if term in keywords(e.text, 12)][:MAX_CLUES]
            out.append({"theme": term, "explanation": f"“{term}” appears in {count} of your saved items.",
                        "refs": refs, "missing": "", "next_step": f"Compare how these items treat “{term}”."})
            if len(out) == 4:
                break
        thoughts_missing = [e for e in items if "Missing:" in e.text]
        if thoughts_missing:
            out.append({"theme": "Open questions", "explanation": "You marked information as missing in these thoughts.",
                        "refs": [e.ref for e in thoughts_missing][:MAX_CLUES],
                        "missing": "; ".join(self._field(e.text, "Missing") for e in thoughts_missing[:3]),
                        "next_step": "Look for a source that fills the missing information."})
        return out

    def related_terms(self, query: str) -> list[str]:
        table = {"article": ["paper", "study", "source", "pdf"], "paper": ["article", "study"], "source": ["reference", "article"],
                 "idea": ["thought"], "ideas": ["thoughts"], "discussion": ["argument"], "trust": ["reliance", "confidence"],
                 "review": ["literature"], "notes": ["note"]}
        out = []
        for w in keywords(query, 10):
            out += table.get(w, [])
        return sorted(set(out) - set(keywords(query, 10)))


# --------------------------------------------------------------------------- OpenAI
SYSTEM = """You help a person resume interrupted writing. You may ONLY use the evidence items provided.
Rules: never invent facts, sources, or citations; never claim to know why the user opened a page unless their own note says so;
cite evidence ids exactly as given; at most 3 clues; say clearly when context is incomplete; suggest exactly ONE next step.
Respond with JSON only."""


class OpenAIProvider(PlaceholderProvider):
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        s = get_settings()
        self.client = OpenAI(api_key=s.openai_api_key)
        self.model = s.openai_model

    def _json(self, user: str) -> dict:
        r = self.client.chat.completions.create(model=self.model, temperature=0.2, response_format={"type": "json_object"},
                                                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
        return json.loads(r.choices[0].message.content or "{}")

    def resume(self, ctx: AIContext) -> ResumeProposal:
        schema = ('{"context_guess":{"text":str,"clues":[{"ref":str,"explanation":str,"certainty":"low|medium|high"}],"context_incomplete":bool},'
                  '"next_step":{"text":str,"clues":[...same...],"context_incomplete":bool}}')
        data = self._json(f"Return JSON shaped like {schema}.\ncontext_guess = what the user was probably doing (it is a guess, phrase it as 'You may have been…').\n"
                          f"next_step = one concrete next action.\nEvidence:\n{json.dumps(ctx.payload())}")

        def prop(d: dict) -> Proposal:
            clues = [Clue(str(c.get("ref", "")), str(c.get("explanation", "")), str(c.get("certainty", "medium"))) for c in d.get("clues", [])]
            return Proposal(str(d.get("text", "")).strip(), validate_clues(ctx, clues), bool(d.get("context_incomplete", False)))
        cg, ns = prop(data.get("context_guess", {})), prop(data.get("next_step", {}))
        if not cg.text or not ns.text:
            raise ValueError("incomplete AI response")
        return ResumeProposal(cg, ns, self.name)

    def future_self_question(self, ctx: AIContext, thought: dict | None) -> str:
        data = self._json("Write ONE short question (max 20 words) the user should answer for their future self before a break, "
                          "based on the evidence. If the user already wrote an unfinished thought, ask about something it does not cover. "
                          f'Return {{"question": str}}.\nAlready written thought: {json.dumps(thought or {})}\nEvidence:\n{json.dumps(ctx.payload())}')
        q = str(data.get("question", "")).strip()
        if not q:
            raise ValueError("empty question")
        return q[:300]

    def connections(self, ctx: AIContext) -> list[dict]:
        data = self._json('Find up to 5 connections between the notes, thoughts and sources. Return {"connections":[{"theme":str,'
                          '"explanation":str,"refs":[evidence ids],"missing":str,"next_step":str}]}. Use only given ids.\n'
                          f"Evidence:\n{json.dumps(ctx.payload())}")
        known = ctx.by_ref()
        out = []
        for c in data.get("connections", [])[:5]:
            refs = [r for r in c.get("refs", []) if r in known][:MAX_CLUES]
            if refs:
                out.append({"theme": str(c.get("theme", ""))[:120], "explanation": str(c.get("explanation", ""))[:500],
                            "refs": refs, "missing": str(c.get("missing", ""))[:300], "next_step": str(c.get("next_step", ""))[:300]})
        return out

    def related_terms(self, query: str) -> list[str]:
        data = self._json(f'Give up to 5 related search terms for: {json.dumps(query)}. Return {{"terms":[str]}}.')
        return [str(t)[:40] for t in data.get("terms", [])][:5]


_placeholder = PlaceholderProvider()


def get_provider():
    if get_settings().ai_enabled:
        try:
            return OpenAIProvider()
        except Exception as e:  # pragma: no cover - missing package / bad key format
            log.warning("OpenAI unavailable, using placeholder: %s", e)
    return _placeholder


def call_with_fallback(method: str, *args):
    """Call the configured provider; fall back to the placeholder on any failure."""
    provider = get_provider()
    try:
        return getattr(provider, method)(*args), provider.name
    except Exception as e:
        if provider is _placeholder:
            raise
        log.warning("AI call %s failed, using placeholder: %s", method, e)
        return getattr(_placeholder, method)(*args), "placeholder"
