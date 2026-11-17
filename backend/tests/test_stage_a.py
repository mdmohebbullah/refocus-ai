"""Stage A — the six scenarios end to end (Features 1, 2, 5A-server-side, 7–14)."""
from conftest import PARA, write_doc


# 1. Registration and authentication -------------------------------------------------
def test_register_login_me(client):
    r = client.post("/api/auth/register", json={"email": "Maya@Example.edu", "name": "Maya", "password": "correct-horse-1"})
    assert r.status_code == 201
    assert client.post("/api/auth/register", json={"email": "maya@example.edu", "name": "M", "password": "correct-horse-1"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "maya@example.edu", "password": "wrong-password"}).status_code == 401
    tok = client.post("/api/auth/login", json={"email": "maya@example.edu", "password": "correct-horse-1"}).json()["access_token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["email"] == "maya@example.edu" and me["preferences"]["shortcuts"]["pause_session"] == "Alt+Shift+P"
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_short_password_rejected(client):
    assert client.post("/api/auth/register", json={"email": "a@b.co", "name": "A", "password": "short"}).status_code == 422


# 2. Projects ------------------------------------------------------------------------
def test_project_crud_search_category(client, auth, project):
    pid = project["id"]
    assert project["documents"][0]["title"] == "Main draft"
    client.post("/api/projects", headers=auth, json={"name": "Thesis chapter 2", "category": "dissertation"})
    assert [p["name"] for p in client.get("/api/projects?q=trust", headers=auth).json()["projects"]] == [project["name"]]
    assert len(client.get("/api/projects?category=dissertation", headers=auth).json()["projects"]) == 1
    r = client.patch(f"/api/projects/{pid}", headers=auth, json={"description": "Section 2.3"})
    assert r.json()["description"] == "Section 2.3"
    assert client.post("/api/projects", headers=auth, json={"name": "x", "category": "bogus"}).status_code == 422
    doc = client.post(f"/api/projects/{pid}/documents", headers=auth, json={"title": "Discussion"}).json()
    assert doc["read_only"] is False
    assert client.delete(f"/api/projects/{pid}", headers=auth).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=auth).status_code == 404


# 3. Persistent document saving + auto versions -----------------------------------------
def test_document_saving_and_auto_version(client, auth, project, SessionTest):
    did = project["documents"][0]["id"]
    text = write_doc(client, auth, did)
    d = client.get(f"/api/documents/{did}", headers=auth).json()
    assert d["content_text"] == text and d["cursor_pos"] == len(text)
    from app.models import DocumentVersion
    with SessionTest() as s:
        assert s.query(DocumentVersion).filter_by(document_id=did, reason="auto").count() == 1


# Scenario 1 — Pause and save context (Feature 7) -----------------------------------------
def pause(client, auth, project, **extra):
    did = project["documents"][0]["id"]
    write_doc(client, auth, did)
    draft = client.get(f"/api/projects/{project['id']}/pause-draft", headers=auth,
                       params={"document_id": did, "cursor": 120, "paragraph_text": PARA, "paragraph_index": 2}).json()
    body = {"project_id": project["id"], "document_id": did, "goal": draft["goal"],
            "position": {"cursor": 120, "paragraph_index": 2, "paragraph_text": PARA, "source": "cursor"},
            "included": {"thoughts": [t["id"] for t in draft["thoughts"]]},
            "future_self": {"question": draft["future_self"]["question"], "answer": "B is behavioral, A is a survey.",
                            "generated_by": draft["future_self"]["generated_by"]}}
    body.update(extra)
    r = client.post("/api/checkpoints", headers=auth, json=body)
    assert r.status_code == 201, r.text
    return draft, r.json()


def test_pause_draft_and_checkpoint(client, auth, project):
    draft, cp = pause(client, auth, project)
    for key in ("project", "document", "position", "goal", "tabs", "activity", "thoughts", "notes", "references", "tasks", "source_links"):
        assert key in draft
    assert draft["position"]["provenance_label"] == "Saved by You"
    assert draft["future_self"]["question"].endswith("?")
    assert cp["position"]["paragraph_text"] == PARA and cp["document_version_id"]
    assert cp["future_self"]["answer"] == "B is behavioral, A is a survey."
    assert cp["index"] == 1 and cp["total"] == 1


def test_untick_goal_and_position(client, auth, project):
    _, cp = pause(client, auth, project, included={"include_goal": False, "include_position": False})
    assert cp["goal"] == "" and cp["position"] is None


# Scenario 2 — Unfinished thought (Feature 8) -----------------------------------------------
def test_unfinished_thought_exact_wording_and_navigation(client, auth, project):
    words = "Task difficulty may change how fast people recover — not sure yet!!"
    t1 = client.post("/api/thoughts", headers=auth, json={"project_id": project["id"], "thinking": words,
                                                          "missing": "A study that supports or challenges it."}).json()
    assert t1["thinking"] == words and t1["provenance_label"] == "Saved by You"
    t2 = client.post("/api/thoughts", headers=auth, json={"project_id": project["id"], "thinking": "Second idea"}).json()
    nav = client.get(f"/api/thoughts/{t2['id']}", headers=auth).json()
    assert nav["previous_id"] == t1["id"] and nav["next_id"] is None
    client.patch(f"/api/thoughts/{t1['id']}", headers=auth, json={"completed": True})
    assert [t["id"] for t in client.get(f"/api/thoughts?project_id={project['id']}", headers=auth).json()["thoughts"]] == [t2["id"]]
    assert client.get("/api/thoughts?q=difficulty&include_completed=true", headers=auth).json()["thoughts"][0]["id"] == t1["id"]
    assert client.post("/api/thoughts", headers=auth, json={"project_id": project["id"]}).status_code == 422


def test_thought_saved_with_checkpoint(client, auth, project):
    _, cp = pause(client, auth, project, new_thought={"project_id": project["id"], "thinking": "Divergence of measures",
                                                      "missing": "a third study", "next_plan": "search Scholar"})
    assert cp["thoughts"][0]["thinking"] == "Divergence of measures"


# Feature 9 — Future-self question avoids repeating the thought -----------------------------
def test_future_self_question_adapts(client, auth, project):
    pid = project["id"]
    q1 = client.get(f"/api/projects/{pid}/pause-draft", headers=auth, params={"paragraph_text": PARA}).json()["future_self"]["question"]
    client.post("/api/thoughts", headers=auth, json={"project_id": pid, "thinking": "measures may diverge"})
    q2 = client.get(f"/api/projects/{pid}/pause-draft", headers=auth).json()["future_self"]["question"]
    assert q1 != q2 and "missing" in q2.lower()


def test_future_self_skip(client, auth, project):
    _, cp = pause(client, auth, project)
    r = client.put(f"/api/checkpoints/{cp['id']}/future-self", headers=auth, json={"question": "Edited?", "question_edited": True,
                                                                                    "answer": "ignored", "skipped": True})
    assert r.json()["answer"] == "" and r.json()["question_provenance"] == "Saved by You"


# Scenario 3 — Resume card (Feature 10, 14) ----------------------------------------------------
def test_resume_card_separates_facts_and_guesses(client, auth, project):
    pause(client, auth, project, new_thought={"project_id": project["id"], "thinking": "self-report vs reliance",
                                              "next_plan": "explain why the two measures diverge"})
    card = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    assert card["facts"]["goal"]["provenance_label"] == "Saved by You"
    assert card["facts"]["position"]["provenance_label"] == "Saved by You"
    assert card["facts"]["future_self"]["answer"]
    assert card["ai"]["context_guess"]["provenance_label"] == "AI Guess"
    assert card["ai"]["next_step"]["provenance_label"] == "AI Suggestion"
    assert "explain why the two measures diverge" in card["ai"]["next_step"]["display_text"]
    assert card["ai"]["next_step"]["provider_label"].startswith("Placeholder")
    assert card["time"]["help_level"] in ("brief", "balanced", "detailed")
    # cached: same suggestion on reload
    again = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    assert again["ai"]["next_step"]["id"] == card["ai"]["next_step"]["id"]


def test_resume_writing_restores_cursor(client, auth, project):
    _, cp = pause(client, auth, project)
    r = client.post(f"/api/checkpoints/{cp['id']}/resume-writing", headers=auth).json()
    assert r["mode"] == "editor" and r["cursor"] == 120 and r["highlight_text"] == PARA


def test_resume_without_checkpoint_marks_incomplete(client, auth, project):
    card = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    assert card["checkpoint"] is None and card["context_incomplete"] is True and card["incomplete_reasons"]


# Scenario 4 — Why? at most three clues, all real evidence (Feature 11) ------------------------
def test_why_clues_max_three_and_cite_real_evidence(client, auth, project):
    pid = project["id"]
    for i in range(4):
        client.post("/api/thoughts", headers=auth, json={"project_id": pid, "thinking": f"trust measurement idea {i}"})
    _, cp = pause(client, auth, project)
    card = client.get(f"/api/projects/{pid}/resume", headers=auth).json()
    for key in ("context_guess", "next_step"):
        s = card["ai"][key]
        assert 1 <= s["clue_count"] <= 3
        assert s["clue_heading"] == f"Based on {s['clue_count']} clue{'s' if s['clue_count'] != 1 else ''}"
        for c in s["clues"]:
            assert c["type"] in ("thought", "note", "goal", "activity", "source", "checkpoint")
            assert c["certainty"] in ("low", "medium", "high") and c["explanation"]


def test_validate_clues_drops_fabricated_refs():
    from app.ai.context import AIContext, Evidence
    from app.ai.provider import Clue, validate_clues
    ctx = AIContext(1, "p", None, evidence=[Evidence("thought:1", "thought", "t", "x"), Evidence("note:2", "note", "n", "y")])
    out = validate_clues(ctx, [Clue("source:999", "made up"), Clue("thought:1", "ok"), Clue("thought:1", "dup"),
                               Clue("note:2", "ok"), Clue("goal:project", "not in context")])
    assert [c.ref for c in out] == ["thought:1", "note:2"]


def test_only_one_clue_shows_singular_heading(client, auth):
    p = client.post("/api/projects", headers=auth, json={"name": "Tiny", "goal": ""}).json()
    client.post("/api/thoughts", headers=auth, json={"project_id": p["id"], "thinking": "lonely idea"})
    s = client.get(f"/api/projects/{p['id']}/resume", headers=auth).json()["ai"]["next_step"]
    assert s["clue_count"] == 1 and s["clue_heading"] == "Based on 1 clue"


# Scenario 5 — Help levels (Feature 12) + time-away suggestion (15) ------------------------------
def test_help_level_preference_overrides_suggestion(client, auth, project):
    card = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    assert card["time"]["help_level_source"] == "time_away_suggestion"
    client.patch("/api/me/preferences", headers=auth, json={"help_level": "brief"})
    card = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    assert card["time"]["help_level"] == "brief" and card["time"]["help_level_source"] == "user_preference"
    client.patch("/api/me/preferences", headers=auth, json={"clear_help_level": True})
    assert client.get("/api/me", headers=auth).json()["preferences"]["help_level"] is None


def test_time_away_table():
    from app.timekeeping import suggest_for_minutes
    assert suggest_for_minutes(5)["suggested_help_level"] == "brief"
    assert suggest_for_minutes(30)["suggested_help_level"] == "brief"
    assert suggest_for_minutes(120)["suggested_help_level"] == "balanced"
    assert suggest_for_minutes(600)["suggested_help_level"] == "detailed"
    assert suggest_for_minutes(3000)["recommended_resume"] == "Comprehensive summary"


# Scenario 6 — Accept / Partly / Reject (Feature 13) ------------------------------------------------
def test_partly_requires_text_and_becomes_user_confirmed(client, auth, project):
    pause(client, auth, project)
    step = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()["ai"]["next_step"]
    assert client.post(f"/api/suggestions/{step['id']}/feedback", headers=auth, json={"verdict": "partly"}).status_code == 422
    r = client.post(f"/api/suggestions/{step['id']}/feedback", headers=auth,
                    json={"verdict": "partly", "correction": "Check the discussion paragraph first.", "make_task": True}).json()
    assert r["provenance_label"] == "User Confirmed" and r["display_text"] == "Check the discussion paragraph first."
    tasks = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()["tasks"]
    assert tasks[0]["title"] == "Check the discussion paragraph first." and tasks[0]["provenance_label"] == "User Confirmed"


def test_rejected_guess_never_shown_as_information(client, auth, project):
    pause(client, auth, project)
    card = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    gid = card["ai"]["context_guess"]["id"]
    r = client.post(f"/api/suggestions/{gid}/feedback", headers=auth, json={"verdict": "reject"}).json()
    assert r["status"] == "rejected" and r["display_text"] is None and r["ai_text"] is None
    card2 = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()
    assert card2["ai"]["context_guess"]["id"] != gid  # a fresh guess, the rejected one is not reused


def test_accept(client, auth, project):
    pause(client, auth, project)
    step = client.get(f"/api/projects/{project['id']}/resume", headers=auth).json()["ai"]["next_step"]
    r = client.post(f"/api/suggestions/{step['id']}/feedback", headers=auth, json={"verdict": "accept"}).json()
    assert r["status"] == "accepted" and r["provenance_label"] == "User Confirmed"


# Data isolation ----------------------------------------------------------------------------------
def test_other_user_cannot_see_anything(client, auth, other_auth, project):
    _, cp = pause(client, auth, project)
    t = client.post("/api/thoughts", headers=auth, json={"project_id": project["id"], "thinking": "private"}).json()
    for url in (f"/api/projects/{project['id']}", f"/api/checkpoints/{cp['id']}", f"/api/thoughts/{t['id']}",
                f"/api/documents/{project['documents'][0]['id']}", f"/api/projects/{project['id']}/resume"):
        assert client.get(url, headers=other_auth).status_code == 404, url
    assert client.get("/api/projects", headers=other_auth).json()["projects"] == []
    assert client.post("/api/thoughts", headers=other_auth, json={"project_id": project["id"], "thinking": "x"}).status_code == 404
