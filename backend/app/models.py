"""Relational schema for Re-Focus AI.

User-authored content and AI-generated content are stored in separate columns/tables.
All timestamps are stored in UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat naive values as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)


def owner_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def project_fk(nullable: bool = False) -> Mapped[Any]:
    return mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=nullable)


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))

    preferences: Mapped[UserPreferences] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    privacy: Mapped[PrivacySettings] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)


class Project(Timestamped, Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60), default="general")  # research_paper | assignment | dissertation | literature_review | general
    description: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")  # Saved by You
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Timestamped, Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default="builtin")  # builtin | google_docs | word
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # TipTap JSON (builtin only)
    content_text: Mapped[str] = mapped_column(Text, default="")
    cursor_pos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    connected_account_id: Mapped[int | None] = mapped_column(ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(String(30), default="auto")  # auto | checkpoint | before_restore | restore
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ExternalDocumentSnapshot(Base):
    __tablename__ = "external_document_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    checkpoint_id: Mapped[int | None] = mapped_column(ForeignKey("checkpoints.id", ondelete="SET NULL"), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    paragraphs: Mapped[list] = mapped_column(JSON, default=list)  # [{index, text, heading_id?, style?}]
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class WorkSession(Base):
    __tablename__ = "work_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused | ended


class TimeTrackingRecord(Base):
    __tablename__ = "time_tracking_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    session_id: Mapped[int | None] = mapped_column(ForeignKey("work_sessions.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))  # active | away
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="app")  # app | extension | manual
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int | None] = project_fk(nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("device_connections.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="page_visit")  # page_visit | app_session
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    content_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)  # only with explicit content permission
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_activity_user_time", "user_id", "occurred_at"),)


class BrowserTab(Base):
    __tablename__ = "browser_tabs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    device_id: Mapped[int | None] = mapped_column(ForeignKey("device_connections.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id: Mapped[int | None] = project_fk(nullable=True)
    tab_id: Mapped[int] = mapped_column(Integer)
    window_id: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(1000), default="")
    url: Mapped[str] = mapped_column(String(2000), default="")
    domain: Mapped[str] = mapped_column(String(300), default="")
    fav_icon_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    content_available: Mapped[bool] = mapped_column(Boolean, default=False)
    content_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("device_id", "tab_id", name="uq_device_tab"),)


class Checkpoint(Timestamped, Base):
    __tablename__ = "checkpoints"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    document_version_id: Mapped[int | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True)
    label: Mapped[str] = mapped_column(String(300), default="")
    goal: Mapped[str] = mapped_column(Text, default="")  # Saved by You
    # position: {cursor?, paragraph_index?, paragraph_text, source: cursor|user_marked|ai_guess, heading_id?}
    position: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    included: Mapped[dict] = mapped_column(JSON, default=dict)  # which item ids the user kept (checklist)
    break_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceSelection(Base):
    __tablename__ = "source_selections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("checkpoints.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # tab | activity | reference
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(1000), default="")
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class UnfinishedThought(Timestamped, Base):
    __tablename__ = "unfinished_thoughts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    checkpoint_id: Mapped[int | None] = mapped_column(ForeignKey("checkpoints.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    thinking: Mapped[str] = mapped_column(Text, default="")  # exact user wording
    missing: Mapped[str] = mapped_column(Text, default="")
    next_plan: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reference_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_urls: Mapped[list] = mapped_column(JSON, default=list)
    origin: Mapped[str] = mapped_column(String(10), default="typed")  # typed | voice | quick
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class FutureSelfQuestion(Timestamped, Base):
    __tablename__ = "future_self_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("checkpoints.id", ondelete="CASCADE"), unique=True)
    question: Mapped[str] = mapped_column(Text)
    question_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    answer: Mapped[str] = mapped_column(Text, default="")
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_by: Mapped[str] = mapped_column(String(20), default="placeholder")


class UserNote(Timestamped, Base):
    __tablename__ = "user_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    checkpoint_id: Mapped[int | None] = mapped_column(ForeignKey("checkpoints.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")


class Reference(Timestamped, Base):
    __tablename__ = "references"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    title: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    authors: Mapped[str] = mapped_column(String(1000), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    why_saved: Mapped[str] = mapped_column(Text, default="")  # user-written
    ai_relevance: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-inferred, shown separately
    thought_ids: Mapped[list] = mapped_column(JSON, default=list)
    checkpoint_ids: Mapped[list] = mapped_column(JSON, default=list)


class Task(Timestamped, Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    checkpoint_id: Mapped[int | None] = mapped_column(ForeignKey("checkpoints.id", ondelete="SET NULL"), nullable=True)
    suggestion_id: Mapped[int | None] = mapped_column(ForeignKey("ai_suggestions.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | dismissed
    origin: Mapped[str] = mapped_column(String(20), default="user")  # user | ai_suggestion | user_confirmed


class AISuggestion(Timestamped, Base):
    __tablename__ = "ai_suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int] = project_fk()
    checkpoint_id: Mapped[int | None] = mapped_column(ForeignKey("checkpoints.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30), default="next_step")  # next_step | context_guess | position_guess | research_connection
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | accepted | partly | rejected
    user_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # user's own step (User Confirmed)
    provider: Mapped[str] = mapped_column(String(20), default="placeholder")
    context_incomplete: Mapped[bool] = mapped_column(Boolean, default=False)

    evidence: Mapped[list[SuggestionEvidence]] = relationship(back_populates="suggestion", cascade="all, delete-orphan", order_by="SuggestionEvidence.rank")


class SuggestionEvidence(Base):
    __tablename__ = "suggestion_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_id: Mapped[int] = mapped_column(ForeignKey("ai_suggestions.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    evidence_type: Mapped[str] = mapped_column(String(30))  # thought | note | goal | activity | source | checkpoint
    evidence_ref: Mapped[str] = mapped_column(String(60))  # e.g. "thought:12"
    label: Mapped[str] = mapped_column(String(500))
    explanation: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    certainty: Mapped[str] = mapped_column(String(10), default="medium")  # low | medium | high

    suggestion: Mapped[AISuggestion] = relationship(back_populates="evidence")


class SuggestionFeedback(Base):
    __tablename__ = "suggestion_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    suggestion_id: Mapped[int] = mapped_column(ForeignKey("ai_suggestions.id", ondelete="CASCADE"), index=True)
    verdict: Mapped[str] = mapped_column(String(10))  # accept | partly | reject
    correction: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PinnedItem(Base):
    __tablename__ = "pinned_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    project_id: Mapped[int | None] = project_fk(nullable=True)
    item_type: Mapped[str] = mapped_column(String(20))  # project | thought | note | goal | reference | task
    item_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "item_type", "item_id", name="uq_pin"),)


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    help_level: Mapped[str | None] = mapped_column(String(10), nullable=True)  # None = follow time-away suggestion
    theme: Mapped[str] = mapped_column(String(10), default="system")
    current_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    break_threshold_minutes: Mapped[int] = mapped_column(Integer, default=10)
    break_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    inactivity_gap_minutes: Mapped[int] = mapped_column(Integer, default=5)  # gaps longer than this count as "away"
    shortcuts: Mapped[dict] = mapped_column(JSON, default=dict)
    voice_upload_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="preferences")


class PrivacySettings(Base):
    __tablename__ = "privacy_settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    private_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    activity_collection: Mapped[bool] = mapped_column(Boolean, default=True)
    excluded_domains: Mapped[list] = mapped_column(JSON, default=list)  # user additions
    removed_default_exclusions: Mapped[list] = mapped_column(JSON, default=list)
    remember_tab_preferences: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_domains: Mapped[list] = mapped_column(JSON, default=list)
    history_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="privacy")


class DeviceConnection(Base):
    __tablename__ = "device_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="extension")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    collection_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    content_access: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    provider: Mapped[str] = mapped_column(String(20))  # google | microsoft
    account_email: Mapped[str] = mapped_column(String(320), default="")
    scopes: Mapped[str] = mapped_column(Text, default="")
    token_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_account_provider"),)


class OAuthState(Base):
    """Short-lived CSRF state for OAuth connections."""
    __tablename__ = "oauth_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = owner_fk()
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
