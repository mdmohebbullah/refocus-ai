# Re-Focus AI — Architecture (Version 1)

**Capture → Review → Resume.** Never make an AI guess look like a memory.

## 1. System overview

```
┌──────────────────────┐      HTTPS / JSON      ┌───────────────────────────────┐
│  Web app (React/TS)  │ ─────────────────────▶ │  API (FastAPI)                │
│  Vite · Tailwind     │ ◀───────────────────── │  routers/ (REST)              │
│  TipTap editor       │                        │  ai/context.py  ← approved     │
│  Panel stack (5A)    │                        │     evidence only             │
└──────────────────────┘                        │  ai/provider.py (OpenAI |      │
          ▲                                      │     placeholder)               │
          │ opens dashboard                      │  integrations/ (Google, MS,    │
┌──────────────────────┐   device token          │     .docx) — read-only         │
│ Chrome extension MV3 │ ─────────────────────▶ │  SQLAlchemy + Alembic          │
│ popup · service      │  tabs / history meta   └──────────────┬────────────────┘
│ worker · idle        │                                        │
└──────────────────────┘                          PostgreSQL (SQLite for local dev)
```

## 2. Folder structure

```
refocus-ai/
  backend/
    app/
      main.py            FastAPI app, router registration, CORS
      config.py          settings from environment variables
      db.py              engine, session, Base
      models.py          all 24 tables
      schemas.py         Pydantic request/response models
      security.py        password hashing, JWT, token encryption
      deps.py            current user / device dependencies
      provenance.py      label constants (Saved by You, AI Guess, …)
      privacy.py         exclusion rules, sensitive-site defaults
      timekeeping.py     active time, time away, suggested help level
      ai/
        context.py       builds the AI context from approved evidence ONLY
        provider.py      OpenAI provider + deterministic placeholder provider
        service.py       suggestions, clues, future-self question, connections
      integrations/
        google_docs.py   OAuth + read-only Docs API
        microsoft_word.py OAuth + read-only Graph API
        docx_reader.py   .docx text extraction
      routers/           auth, projects, documents, checkpoints, thoughts, resume,
                         suggestions, activity, tabs, history, research, tasks,
                         pins, search, time, privacy, devices, integrations, voice, sync
    alembic/             migrations
    tests/               pytest suite (per stage)
  frontend/
    src/
      api/               typed client
      components/        UI kit, provenance labels, panel host
      panels/            Pause, FutureSelf, Thought, ResumeCard, Why, Source,
                         HelpLevel, ReviewSuggestion, Share/History panels
      pages/             12 sidebar sections + editor
      hooks/             shortcuts, idle/break detection, heartbeat, sync
      state/             panel stack (Back/Forward)
  extension/             Manifest V3 extension
  docs/                  architecture, API, test report
```

## 3. Data model (key relationships)

```
User 1─* Project 1─* Document 1─* DocumentVersion
                 │            └─* ExternalDocumentSnapshot (Google/Word, read-only)
                 ├─* Checkpoint 1─1 FutureSelfQuestion
                 │      ├─* UnfinishedThought
                 │      ├─* SourceSelection (tabs / activity / references chosen at pause)
                 │      └─* AISuggestion 1─* SuggestionEvidence (≤3 clues)
                 │                        1─* SuggestionFeedback
                 ├─* UserNote, Reference, Task, PinnedItem
                 └─* WorkSession 1─* TimeTrackingRecord
User 1─* ActivityEvent, BrowserTab, DeviceConnection, ConnectedAccount
User 1─1 UserPreferences, PrivacySettings
```

User-authored content (thoughts, notes, `why_saved`, goals, corrections) lives in its own
columns/tables. AI output lives only in `ai_suggestions`, `suggestion_evidence`,
`references.ai_relevance`, and position fields whose `position_source = "ai_guess"`.

## 4. AI context processing

1. `ai/context.py` gathers the six evidence types for a project/checkpoint.
2. It drops anything excluded: deselected tabs/activity, user-excluded domains, default
   sensitive sites, private-mode periods, and items the user unticked at pause.
3. Each evidence item gets a stable id (`thought:12`, `activity:40`, …).
4. The provider must answer with structured JSON that cites evidence ids. Any clue that
   cites an id not in the context is discarded, and at most three clues are kept.
5. With no `OPENAI_API_KEY`, a deterministic placeholder provider is used and every
   output is labelled "Placeholder AI".

## 5. Navigation model

* **5A Panel Back/Forward** — client-side stack of `{panel, props, state}` entries.
  Panels keep their form state inside their stack entry, so returning restores it.
* **5B Checkpoint timeline** — server-ordered checkpoints; Older/Newer, slider,
  compare, non-destructive restore (current content is versioned first).

## 6. Build stages

| Stage | Features |
|---|---|
| A | 1, 2, 5A, 7–14 — the six scenarios end to end |
| B | 3, 4, 15–17 + Google Docs / Word read-only |
| C | 5B, 6, 19–22 |
| D | 18, 23, deployment, docs |
