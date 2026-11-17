export type Provenance = 'saved_by_you' | 'recorded_activity' | 'ai_guess' | 'ai_suggestion' | 'user_confirmed'
export type HelpLevel = 'brief' | 'balanced' | 'detailed'

export interface Prov { provenance: Provenance; provenance_label: string }

export interface Project {
  id: number; name: string; category: string; description: string; goal: string; pinned: boolean
  last_active_at: string | null; created_at: string; updated_at: string; documents?: Doc[]
}
export interface Doc {
  id: number; project_id: number; title: string; source: 'builtin' | 'google_docs' | 'word'; read_only: boolean
  external_url: string | null; cursor_pos: number | null; updated_at: string; word_count: number
  content_json?: any; content_text?: string
}
export interface Position extends Partial<Prov> {
  cursor?: number | null; paragraph_index?: number | null; paragraph_text: string; heading_id?: string | null
  source: 'cursor' | 'user_marked' | 'ai_guess'
}
export interface Thought extends Prov {
  id: number; project_id: number; checkpoint_id: number | null; document_id: number | null
  thinking: string; missing: string; next_plan: string; position: Position | null
  reference_ids: number[]; source_urls: string[]; origin: string; completed: boolean; pinned: boolean
  created_at: string; updated_at: string
}
export interface Clue {
  rank: number; type: string; type_label: string; ref: string; label: string; explanation: string
  excerpt: string; url: string | null; certainty: 'low' | 'medium' | 'high'
}
export interface Suggestion extends Prov {
  id: number; kind: string; checkpoint_id: number | null; status: 'pending' | 'accepted' | 'partly' | 'rejected'
  ai_text: string | null; user_text: string | null; display_text: string | null; provider: string; provider_label: string
  context_incomplete: boolean; clue_count: number; clue_heading: string; clues: Clue[]; created_at: string
}
export interface FutureSelf {
  id: number; question: string; question_edited: boolean; answer: string; skipped: boolean; generated_by: string
  question_provenance: string; answer_provenance: string
}
export interface Checkpoint {
  id: number; project_id: number; document_id: number | null; document_version_id: number | null; label: string; goal: string
  position: Position | null; included: Record<string, any>; created_at: string; break_started_at: string | null
  resumed_at: string | null; index: number; total: number; older_id?: number | null; newer_id?: number | null
  future_self?: FutureSelf | null; sources?: { kind: string; ref_id: number; title: string; url: string | null; provenance_label: string }[]
  thoughts?: Thought[]
}
export interface TimeStatus {
  project_id: number; last_active_at: string | null; returned_at: string; minutes_away: number | null; active_now: boolean
  current_session_seconds: number; total_recorded_seconds: number; basis: string
  recommended_resume: string; suggested_help_level: HelpLevel; help_level: HelpLevel
  help_level_source: 'user_preference' | 'time_away_suggestion'
}
export interface Task extends Prov {
  id: number; project_id: number; checkpoint_id: number | null; suggestion_id: number | null; title: string
  status: 'open' | 'done' | 'dismissed'; origin: string; pinned: boolean; updated_at: string
}
export interface Note extends Prov { id: number; project_id: number; checkpoint_id: number | null; title: string; body: string; pinned: boolean; updated_at: string }
export interface Reference {
  id: number; project_id: number; title: string; url: string | null; authors: string; year: number | null
  why_saved: string; ai_relevance: string | null; thought_ids: number[]; checkpoint_ids: number[]; pinned: boolean; updated_at: string
}
export interface Activity extends Prov {
  id: number; project_id: number | null; kind: string; title: string | null; url: string | null; domain: string | null
  occurred_at: string; selected: boolean; excluded: boolean; status: string
}
export interface Tab extends Prov {
  id: number; tab_id: number; window_id: number; device_id: number | null; project_id: number | null
  title: string | null; url: string | null; domain: string; fav_icon_url: string | null; status: string
  selected: boolean; excluded: boolean; content_available: boolean; last_seen_at: string
}
export interface ResumeCard {
  project: Project
  checkpoint: Checkpoint | null
  timeline: { index: number; total: number; older_id: number | null; newer_id: number | null }
  document: (Doc & { open_url: string | null }) | null
  time: TimeStatus
  facts: {
    goal: ({ text: string } & Prov) | null
    position: Position | null
    thoughts: Thought[]
    future_self: FutureSelf | null
    sources: ({ kind: string; ref_id: number; title: string; url: string | null } & Prov)[]
  }
  ai: { context_guess: Suggestion; next_step: Suggestion }
  context_incomplete: boolean
  incomplete_reasons: string[]
  tasks: Task[]
  pinned: { item_type: string; item: any }[]
}
export interface Me {
  id: number; email: string; name: string
  preferences: {
    help_level: HelpLevel | null; theme: 'light' | 'dark' | 'system'; current_project_id: number | null
    break_threshold_minutes: number; break_reminders: boolean; inactivity_gap_minutes: number
    shortcuts: Record<string, string>; voice_upload_allowed: boolean
  }
  privacy: { private_mode: boolean; activity_collection: boolean }
}
