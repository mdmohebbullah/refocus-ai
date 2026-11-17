"""Stage C — history, checkpoint timeline, version comparison, notes/references, research connections,
smart search, tasks, pins, shortcuts (Features 5B, 6, 19–22)."""
from datetime import timedelta

from app.models import utcnow
from conftest import write_doc
from test_stage_a import pause
from test_stage_b import device, events


# 8–11. Checkpoint timeline navigation + restoration ------------------------------------------
def test_timeline_older_newer_and_nondestructive_restore(client, auth, project):
    did = project["documents"][0]["id"]
    _, c1 = pause(client, auth, project)
    write_doc(client, auth, did, "Version two of the text.")
    c2 = client.post("/api/checkpoints", headers=auth, json={"project_id": project["id"], "document_id": did}).json()
    write_doc(client, auth, did, "Version three, newest.")
    c3 = client.post("/api/checkpoints", headers=auth, json={"project_id": project["id"], "document_id": did}).json()
    d = client.get(f"/api/checkpoints/{c2['id']}", headers=auth).json()
    assert (d["index"], d["total"], d["older_id"], d["newer_id"]) == (2, 3, c1["id"], c3["id"])
    first = client.get(f"/api/checkpoints/{c1['id']}", headers=auth).json()
    assert first["older_id"] is None
    assert client.get(f"/api/checkpoints/{c3['id']}", headers=auth).json()["newer_id"] is None
    card = client.get(f"/api/projects/{project['id']}/resume?checkpoint_id={c1['id']}", headers=auth).json()
    assert card["timeline"] == {"index": 1, "total": 3, "older_id": None, "newer_id": c2["id"]}
    # restore checkpoint 1: current text is kept as a version first, newer checkpoints survive
    r = client.post(f"/api/checkpoints/{c1['id']}/restore", headers=auth).json()
    assert "Study A" in r["document"]["content_text"] and r["backup_version_id"]
    assert client.get(f"/api/projects/{project['id']}/checkpoints", headers=auth).json()["total"] == 3
    cmp = client.get(f"/api/documents/{did}/compare?a=v{r['backup_version_id']}&b=current", headers=auth).json()
    assert cmp["a_text"] == "Version three, newest." and cmp["words_added"] > 0 and cmp["words_removed"] > 0


# 23. Before / after comparison -------------------------------------------------------------
def test_versions_compare_restore(client, auth, project):
    did = project["documents"][0]["id"]
    write_doc(client, auth, did, "alpha beta gamma")
    pause(client, auth, project)  # creates a checkpoint version
    write_doc(client, auth, did, "alpha delta gamma epsilon")
    vs = client.get(f"/api/documents/{did}/versions", headers=auth).json()["versions"]
    assert len(vs) >= 2 and not client.get(f"/api/documents/{did}/versions", headers=auth).json()["read_only"]
    old = vs[-1]["key"]
    cmp = client.get(f"/api/documents/{did}/compare?a={old}&b=current", headers=auth).json()
    assert cmp["words_added"] >= 1 and cmp["words_removed"] >= 1
    vid = int(old[1:])
    r = client.post(f"/api/documents/{did}/versions/{vid}/restore", headers=auth).json()
    assert r["document"]["content_text"] == "alpha beta gamma"
    reasons = [v["reason"] for v in client.get(f"/api/documents/{did}/versions", headers=auth).json()["versions"]]
    assert "before_restore" in reasons and "restore" in reasons
    assert client.get(f"/api/documents/{did}/compare?a=v99999", headers=auth).status_code == 404


# 7. Complete activity history ----------------------------------------------------------------
def test_history_filters_distinguish_work_and_browser(client, auth, project):
    dh, _ = device(client, auth)
    client.post("/api/time/heartbeat", headers=auth, json={"project_id": project["id"]})
    pause(client, auth, project, new_thought={"project_id": project["id"], "thinking": "divergent measures idea"})
    client.post("/api/activity/batch", headers=dh, json={"events": events([2], base="https://nature.com/a") + events([3], base="https://arxiv.org/b")})
    h = client.get("/api/history", headers=auth).json()["items"]
    groups = {i["group"] for i in h}
    assert {"Recorded work session", "Browser metadata"} <= groups
    assert {i["provenance_label"] for i in h if i["kind"] == "browser"} == {"Recorded Activity"}
    assert all(i["kind"] == "browser" for i in client.get("/api/history?website=nature.com", headers=auth).json()["items"])
    assert [i["kind"] for i in client.get("/api/history?q=divergent", headers=auth).json()["items"]] == ["thought"]
    today = utcnow().date().isoformat()
    assert len(client.get(f"/api/history?date_from={today}&date_to={today}", headers=auth).json()["items"]) >= 4
    old = (utcnow() - timedelta(days=10)).date().isoformat()
    assert client.get(f"/api/history?date_from={old}&date_to={old}", headers=auth).json()["items"] == []
    cal = client.get(f"/api/history/calendar?month={today[:7]}", headers=auth).json()["days"]
    assert any(d["browser"] == 2 and d["work"] >= 2 for d in cal)
    # delete one record, then clear a range
    bid = next(i["id"] for i in h if i["kind"] == "browser")
    assert client.delete(f"/api/activity/{bid}", headers=auth).status_code == 204
    r = client.post("/api/history/clear", headers=auth, json={"start": (utcnow() - timedelta(hours=1)).isoformat(), "end": utcnow().isoformat()}).json()
    assert r["removed"]["browser"] == 1
    assert not [i for i in client.get("/api/history", headers=auth).json()["items"] if i["kind"] == "browser"]


def test_history_retention(client, auth, SessionTest):
    dh, _ = device(client, auth)
    client.post("/api/activity/batch", headers=dh, json={"events": [{"title": "old", "url": "https://x.org/old", "occurred_at": (utcnow() - timedelta(days=40)).isoformat()}]})
    assert client.get("/api/history?kinds=browser", headers=auth).json()["items"] == []  # 30-day default retention purged it


# 20–21. Notes, references, research connections ------------------------------------------------
def test_notes_references_separation_and_links(client, auth, project):
    pid = project["id"]
    _, cp = pause(client, auth, project, new_thought={"project_id": pid, "thinking": "reliance vs reported trust"})
    th = cp["thoughts"][0]["id"]
    n = client.post("/api/notes", headers=auth, json={"project_id": pid, "title": "Measures", "body": "Self-report trust scales vs observed reliance"}).json()
    assert n["provenance_label"] == "Saved by You"
    r = client.post("/api/references", headers=auth, json={"project_id": pid, "title": "Trust in automation", "url": "https://doi.org/10.1/xyz",
                    "authors": "Lee & See", "year": 2004, "why_saved": "Defines reliance on automation", "thought_ids": [th], "checkpoint_ids": [cp["id"]]}).json()
    assert r["why_saved_provenance"] == "Saved by You" and r["ai_relevance"] is None and r["thought_ids"] == [th]
    assert client.post("/api/references", headers=auth, json={"project_id": pid, "title": "x", "year": 99}).status_code == 422
    assert client.get(f"/api/references?project_id={pid}&q=reliance", headers=auth).json()["references"][0]["id"] == r["id"]
    assert client.get(f"/api/notes?project_id={pid}&q=observed", headers=auth).json()["notes"][0]["id"] == n["id"]
    conn = client.post(f"/api/projects/{pid}/connect-research", headers=auth).json()
    assert conn["connections"], conn
    for c in conn["connections"]:
        assert c["provenance_label"] == "AI Suggestion" and 1 <= len(c["evidence"]) <= 3


# 24. Smart search -----------------------------------------------------------------------------
def test_smart_search_examples(client, auth, project):
    pid = project["id"]
    dh, _ = device(client, auth)
    yesterday = utcnow() - timedelta(days=1)
    client.post("/api/activity/batch", headers=dh, json={"events": [
        {"title": "Explainable AI and trust — research article", "url": "https://journal.org/article1", "occurred_at": yesterday.isoformat()},
        {"title": "Today page", "url": "https://journal.org/today", "occurred_at": utcnow().isoformat()}]})
    client.post("/api/thoughts", headers=auth, json={"project_id": pid, "thinking": "The two trust measures may diverge"})
    client.post("/api/references", headers=auth, json={"project_id": pid, "title": "Lee & See 2004", "why_saved": "for the discussion section"})
    r1 = client.get("/api/search", headers=auth, params={"q": "Find the research article I opened yesterday."}).json()
    assert [x["title"] for x in r1["results"]] == ["Explainable AI and trust — research article"]
    assert r1["results"][0]["match"] == "stored_record"
    r2 = client.get("/api/search", headers=auth, params={"q": "Show my unfinished ideas about the literature review."}).json()
    assert r2["interpreted"]["project"] == project["name"] and r2["results"][0]["type"] == "thought"
    r3 = client.get("/api/search", headers=auth, params={"q": "Which sources did I save for the discussion section?"}).json()
    assert r3["results"][0]["title"] == "Lee & See 2004"
    for x in r3["ai_inferred"]:
        assert x["match"] == "ai_inferred" and x["provenance_label"] == "AI Guess"


def test_search_respects_private_mode_and_exclusions(client, auth, project):
    dh, _ = device(client, auth)
    client.post("/api/activity/batch", headers=dh, json={"events": events([1], base="https://journal.org/x")})
    client.patch("/api/privacy", headers=auth, json={"private_mode": True})
    assert not [x for x in client.get("/api/search?q=page", headers=auth).json()["results"] if x["type"] == "activity"]


# 25. Tasks and pinned items --------------------------------------------------------------------
def test_tasks_and_pins_carry_into_resume(client, auth, project):
    pid = project["id"]
    pause(client, auth, project)
    step = client.get(f"/api/projects/{pid}/resume", headers=auth).json()["ai"]["next_step"]
    t = client.post("/api/tasks", headers=auth, json={"project_id": pid, "title": step["display_text"], "suggestion_id": step["id"]}).json()
    assert t["provenance_label"] == "AI Suggestion"
    t = client.patch(f"/api/tasks/{t['id']}", headers=auth, json={"title": "My edited step"}).json()
    assert t["provenance_label"] == "User Confirmed"
    mine = client.post("/api/tasks", headers=auth, json={"project_id": pid, "title": "Email Dr. Lee"}).json()
    client.patch(f"/api/tasks/{mine['id']}", headers=auth, json={"status": "done"})
    assert [x["title"] for x in client.get(f"/api/tasks?project_id={pid}", headers=auth).json()["tasks"]] == ["My edited step"]
    th = client.post("/api/thoughts", headers=auth, json={"project_id": pid, "thinking": "pinned idea"}).json()
    client.post("/api/pins", headers=auth, json={"item_type": "thought", "item_id": th["id"]})
    client.post("/api/pins", headers=auth, json={"item_type": "goal", "item_id": pid})
    client.post("/api/pins", headers=auth, json={"item_type": "project", "item_id": pid})
    client.post("/api/pins", headers=auth, json={"item_type": "thought", "item_id": th["id"]})  # idempotent
    card = client.get(f"/api/projects/{pid}/resume", headers=auth).json()
    assert {p["item_type"] for p in card["pinned"]} == {"thought", "goal"}
    assert [x["title"] for x in card["tasks"]] == ["My edited step"]  # incomplete tasks carried into the resumed session
    assert client.get("/api/projects", headers=auth).json()["projects"][0]["pinned"] is True
    client.delete(f"/api/pins/thought/{th['id']}", headers=auth)
    assert {p["item_type"] for p in client.get(f"/api/pins?project_id={pid}", headers=auth).json()["pinned"]} == {"goal"}


# Keyboard shortcuts --------------------------------------------------------------------------
def test_shortcuts_configurable_without_browser_conflicts(client, auth):
    r = client.patch("/api/me/preferences", headers=auth, json={"shortcuts": {"search": "Alt+Shift+J"}}).json()
    assert r["preferences"]["shortcuts"]["search"] == "Alt+Shift+J" and r["preferences"]["shortcuts"]["pause_session"] == "Alt+Shift+P"
    assert client.patch("/api/me/preferences", headers=auth, json={"shortcuts": {"panel_back": "Alt+ArrowLeft"}}).status_code == 422
    assert client.patch("/api/me/preferences", headers=auth, json={"shortcuts": {"search": "Ctrl+K"}}).status_code == 422
    assert client.patch("/api/me/preferences", headers=auth, json={"shortcuts": {"search": "Alt+Shift+P"}}).status_code == 422  # duplicate
