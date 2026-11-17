"""Provenance labels. Every piece of content shown to the user carries exactly one."""

SAVED_BY_YOU = "saved_by_you"
RECORDED_ACTIVITY = "recorded_activity"
AI_GUESS = "ai_guess"
AI_SUGGESTION = "ai_suggestion"
USER_CONFIRMED = "user_confirmed"

LABELS = {
    SAVED_BY_YOU: "Saved by You",
    RECORDED_ACTIVITY: "Recorded Activity",
    AI_GUESS: "AI Guess",
    AI_SUGGESTION: "AI Suggestion",
    USER_CONFIRMED: "User Confirmed",
}


def item(kind: str, **fields) -> dict:
    return {"provenance": kind, "provenance_label": LABELS[kind], **fields}
