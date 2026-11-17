from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

HelpLevel = Literal["brief", "balanced", "detailed"]


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    category: str = "general"
    description: str = ""
    goal: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    goal: str | None = None


class DocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class DocumentPatch(BaseModel):
    title: str | None = None
    content_json: dict | None = None
    content_text: str | None = None
    cursor_pos: int | None = None


class Position(BaseModel):
    cursor: int | None = None
    paragraph_index: int | None = None
    paragraph_text: str = ""
    heading_id: str | None = None
    source: Literal["cursor", "user_marked", "ai_guess"] = "cursor"


class ThoughtIn(BaseModel):
    project_id: int
    checkpoint_id: int | None = None
    document_id: int | None = None
    thinking: str = ""
    missing: str = ""
    next_plan: str = ""
    position: Position | None = None
    reference_ids: list[int] = []
    source_urls: list[str] = []
    origin: Literal["typed", "voice", "quick"] = "typed"


class ThoughtPatch(BaseModel):
    thinking: str | None = None
    missing: str | None = None
    next_plan: str | None = None
    completed: bool | None = None
    checkpoint_id: int | None = None
    reference_ids: list[int] | None = None
    source_urls: list[str] | None = None
    position: Position | None = None


class Included(BaseModel):
    """What the user kept ticked in the Pause checklist."""
    tabs: list[int] = []
    activity: list[int] = []
    thoughts: list[int] = []
    notes: list[int] = []
    references: list[int] = []
    tasks: list[int] = []
    include_position: bool = True
    include_goal: bool = True


class FutureSelfIn(BaseModel):
    question: str
    question_edited: bool = False
    answer: str = ""
    skipped: bool = False
    generated_by: str = "placeholder"


class CheckpointIn(BaseModel):
    project_id: int
    document_id: int | None = None
    label: str = ""
    goal: str = ""
    position: Position | None = None
    included: Included = Included()
    new_thought: ThoughtIn | None = None
    future_self: FutureSelfIn | None = None


class FeedbackIn(BaseModel):
    verdict: Literal["accept", "partly", "reject"]
    correction: str = ""
    make_task: bool = False


class PreferencesPatch(BaseModel):
    help_level: HelpLevel | None = None
    clear_help_level: bool = False
    theme: Literal["light", "dark", "system"] | None = None
    current_project_id: int | None = None
    break_threshold_minutes: int | None = Field(default=None, ge=1, le=240)
    break_reminders: bool | None = None
    inactivity_gap_minutes: int | None = Field(default=None, ge=1, le=60)
    shortcuts: dict[str, str] | None = None
    voice_upload_allowed: bool | None = None


class NoteIn(BaseModel):
    project_id: int
    title: str = ""
    body: str = ""
    checkpoint_id: int | None = None


class NotePatch(BaseModel):
    title: str | None = None
    body: str | None = None
    checkpoint_id: int | None = None


class ReferenceIn(BaseModel):
    project_id: int
    title: str = Field(min_length=1)
    url: str | None = None
    authors: str = ""
    year: int | None = None
    why_saved: str = ""
    thought_ids: list[int] = []
    checkpoint_ids: list[int] = []


class ReferencePatch(BaseModel):
    title: str | None = None
    url: str | None = None
    authors: str | None = None
    year: int | None = None
    why_saved: str | None = None
    thought_ids: list[int] | None = None
    checkpoint_ids: list[int] | None = None


class TaskIn(BaseModel):
    project_id: int
    title: str = Field(min_length=1)
    checkpoint_id: int | None = None
    suggestion_id: int | None = None


class TaskPatch(BaseModel):
    title: str | None = None
    status: Literal["open", "done", "dismissed"] | None = None
    checkpoint_id: int | None = None


class PinIn(BaseModel):
    item_type: Literal["project", "thought", "note", "goal", "reference", "task"]
    item_id: int
    project_id: int | None = None


class HeartbeatIn(BaseModel):
    project_id: int
    source: Literal["app", "extension"] = "app"


class TimeCorrectionIn(BaseModel):
    project_id: int
    started_at: datetime
    ended_at: datetime
    kind: Literal["active", "away"] = "active"
    note: str = ""


class TabIn(BaseModel):
    tab_id: int
    window_id: int = 0
    title: str = ""
    url: str = ""
    fav_icon_url: str | None = None
    status: str = "complete"
    has_password_field: bool = False
    content_excerpt: str | None = None


class TabSyncIn(BaseModel):
    tabs: list[TabIn]


class TabSelectIn(BaseModel):
    tab_ids: list[int]
    selected: bool
    project_id: int | None = None


class ActivityIn(BaseModel):
    title: str = ""
    url: str
    occurred_at: datetime
    project_id: int | None = None
    has_password_field: bool = False


class ActivityBatchIn(BaseModel):
    events: list[ActivityIn]


class ActivitySelectIn(BaseModel):
    ids: list[int]
    selected: bool


class PrivacyPatch(BaseModel):
    private_mode: bool | None = None
    activity_collection: bool | None = None
    excluded_domains: list[str] | None = None
    removed_default_exclusions: list[str] | None = None
    remember_tab_preferences: bool | None = None
    approved_domains: list[str] | None = None
    history_retention_days: int | None = Field(default=None, ge=1, le=3650)


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["extension", "web"] = "extension"


class DevicePatch(BaseModel):
    collection_enabled: bool | None = None
    content_access: bool | None = None
    name: str | None = None


class ExternalDocIn(BaseModel):
    project_id: int
    provider: Literal["google", "microsoft"]
    url_or_id: str
    title: str | None = None
