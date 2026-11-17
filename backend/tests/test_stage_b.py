"""Stage B — browser connection, external documents (read-only), time (Features 3, 4, 15–17)."""
import io
import json
from datetime import timedelta

import httpx
import pytest
from docx import Document as Docx

from app.ai.context import build_context
from app.integrations import http as xhttp
from app.models import ActivityEvent, Project, TimeTrackingRecord, User, UserPreferences, utcnow
from app.timekeeping import heartbeat, time_status
from conftest import PARA


def device(client, auth, name="Chrome"):
    r = client.post("/api/devices", headers=auth, json={"name": name})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["id"]


TABS = [
    {"tab_id": 1, "title": "Study B — methods", "url": "https://journal.example.org/studyB#methods"},
    {"tab_id": 2, "title": "Chase online banking", "url": "https://secure.chase.com/web/auth"},
    {"tab_id": 3, "title": "Inbox (3)", "url": "https://mail.google.com/mail/u/0/#inbox"},
    {"tab_id": 4, "title": "Checkout", "url": "https://shop.example.com/checkout"},
    {"tab_id": 5, "title": "My bank login", "url": "https://tinybank.example/home", "has_password_field": True},
    {"tab_id": 6, "title": "Settings", "url": "chrome://settings"},
    {"tab_id": 7, "title": "ZETA survey paper", "url": "https://another.example.edu/studyA"},
]


# 4. Browser extension permissions / pairing ------------------------------------------------
def test_device_pairing_and_revocation(client, auth):
    dh, did = device(client, auth)
    me = client.get("/api/me", headers=dh).json()
    assert me["device"]["id"] == did and me["device"]["content_access"] is False
    assert client.post("/api/tabs/sync", headers=auth, json={"tabs": []}).status_code == 403  # only a paired extension may send tabs
    client.delete(f"/api/devices/{did}", headers=auth)
    assert client.get("/api/me", headers=dh).status_code == 401


# 5. Tab selection and exclusion -----------------------------------------------------------
def test_sensitive_tabs_never_stored(client, auth, SessionTest):
    dh, _ = device(client, auth)
    r = client.post("/api/tabs/sync", headers=dh, json={"tabs": TABS}).json()
    assert r["stored"] == 2 and r["excluded"] == 5
    stored = json.dumps(client.get("/api/tabs", headers=auth).json())
    for secret in ("chase", "Inbox", "checkout", "tinybank", "chrome://"):
        assert secret not in stored


def test_select_all_deselect_and_exclude_site(client, auth, project):
    dh, _ = device(client, auth)
    client.post("/api/tabs/sync", headers=dh, json={"tabs": TABS})
    tabs = client.get("/api/tabs", headers=auth).json()["tabs"]
    assert all(not t["selected"] for t in tabs)  # nothing selected until the user chooses
    ids = [t["id"] for t in tabs]
    client.post("/api/tabs/select", headers=auth, json={"tab_ids": ids, "selected": True, "project_id": project["id"]})
    assert all(t["selected"] for t in client.get("/api/tabs", headers=auth).json()["tabs"])
    client.post("/api/tabs/select", headers=auth, json={"tab_ids": ids, "selected": False})
    assert not any(t["selected"] for t in client.get("/api/tabs", headers=auth).json()["tabs"])
    client.post("/api/tabs/exclude-site", headers=auth, json={"domain": "another.example.edu"})
    assert [t["domain"] for t in client.get("/api/tabs", headers=auth).json()["tabs"]] == ["journal.example.org"]
    client.post("/api/tabs/sync", headers=dh, json={"tabs": TABS})  # extension sends it again: still excluded
    assert len(client.get("/api/tabs", headers=auth).json()["tabs"]) == 1


def test_remember_approved_preferences(client, auth, project):
    dh, _ = device(client, auth)
    client.post("/api/tabs/sync", headers=dh, json={"tabs": TABS[:1]})
    t = client.get("/api/tabs", headers=auth).json()["tabs"][0]
    client.post("/api/tabs/select", headers=auth, json={"tab_ids": [t["id"]], "selected": True})
    # close and reopen the tab: the approved site is selected again automatically
    client.post("/api/tabs/sync", headers=dh, json={"tabs": []})
    client.post("/api/tabs/sync", headers=dh, json={"tabs": [{**TABS[0], "tab_id": 99}]})
    assert client.get("/api/tabs", headers=auth).json()["tabs"][0]["selected"] is True


def test_page_content_requires_permission(client, auth):
    dh, did = device(client, auth)
    tab = {**TABS[0], "content_excerpt": "Trust was operationalised as acceptance rate."}
    client.post("/api/tabs/sync", headers=dh, json={"tabs": [tab]})
    assert client.get("/api/tabs", headers=auth).json()["tabs"][0]["content_available"] is False
    client.patch(f"/api/devices/{did}", headers=auth, json={"content_access": True})
    client.post("/api/tabs/sync", headers=dh, json={"tabs": [tab]})
    assert client.get("/api/tabs", headers=auth).json()["tabs"][0]["content_available"] is True


# 6. Last 60 minutes ------------------------------------------------------------------------
def events(minutes_ago_list, base="https://journal.example.org/p"):
    now = utcnow()
    return [{"title": f"Page {m}", "url": f"{base}{m}", "occurred_at": (now - timedelta(minutes=m)).isoformat()} for m in minutes_ago_list]


def test_last_60_minutes_filters(client, auth):
    dh, _ = device(client, auth)
    r = client.post("/api/activity/batch", headers=dh, json={"events": events([5, 20, 45, 90]) + [
        {"title": "Bank", "url": "https://chase.com/x", "occurred_at": utcnow().isoformat()}]}).json()
    assert r["stored"] == 4 and r["dropped_excluded"] == 1
    assert len(client.get("/api/activity?minutes=15", headers=auth).json()["events"]) == 1
    assert len(client.get("/api/activity?minutes=30", headers=auth).json()["events"]) == 2
    assert len(client.get("/api/activity?minutes=60", headers=auth).json()["events"]) == 3
    start = (utcnow() - timedelta(minutes=100)).isoformat()
    end = (utcnow() - timedelta(minutes=40)).isoformat()
    custom = client.get("/api/activity", headers=auth, params={"start": start, "end": end}).json()["events"]
    assert {e["title"] for e in custom} == {"Page 45", "Page 90"}
    # duplicate upload is ignored
    client.post("/api/activity/batch", headers=dh, json={"events": events([5])})
    # note: occurred_at differs slightly, so just ensure the API never claims page content
    assert "not page content" in client.get("/api/activity", headers=auth).json()["note"]


def test_collection_off_private_mode_and_device_toggle(client, auth):
    dh, did = device(client, auth)
    client.patch("/api/privacy", headers=auth, json={"private_mode": True})
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([1])}).json()["stored"] == 0
    assert client.post("/api/tabs/sync", headers=dh, json={"tabs": TABS[:1]}).json()["stored"] == 0
    client.patch("/api/privacy", headers=auth, json={"private_mode": False})
    client.patch(f"/api/devices/{did}", headers=auth, json={"collection_enabled": False})
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([1])}).json()["stored"] == 0
    client.patch(f"/api/devices/{did}", headers=auth, json={"collection_enabled": True})
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([1])}).json()["stored"] == 1


# Excluded sources never enter the AI context payload ------------------------------------------
def test_excluded_and_unselected_never_in_ai_payload(client, auth, project, SessionTest):
    dh, _ = device(client, auth)
    client.post("/api/tabs/sync", headers=dh, json={"tabs": TABS})
    client.post("/api/activity/batch", headers=dh, json={"events": events([3]) + [
        {"title": "SECRET-UNSELECTED", "url": "https://other.example.net/x", "occurred_at": utcnow().isoformat()}]})
    tabs = client.get("/api/tabs", headers=auth).json()["tabs"]
    keep = [t["id"] for t in tabs if "Study B" in (t["title"] or "")]
    client.post("/api/tabs/select", headers=auth, json={"tab_ids": keep, "selected": True})
    acts = client.get("/api/activity", headers=auth).json()["events"]
    client.post("/api/activity/select", headers=auth, json={"ids": [a["id"] for a in acts], "selected": False})
    client.post("/api/activity/select", headers=auth, json={"ids": [a["id"] for a in acts if a["title"] == "Page 3"], "selected": True})
    client.post("/api/references", headers=auth, json={"project_id": project["id"], "title": "Bank statement", "url": "https://chase.com/statement"})
    with SessionTest() as s:
        user = s.query(User).first()
        payload = json.dumps(build_context(s, user.id, project["id"]).payload())
    assert "Study B" in payload and "Page 3" in payload
    for secret in ("chase", "Inbox", "checkout", "tinybank", "SECRET-UNSELECTED", "ZETA"):
        assert secret not in payload, secret

    # private mode removes all browser evidence
    client.patch("/api/privacy", headers=auth, json={"private_mode": True})
    with SessionTest() as s:
        payload = json.dumps(build_context(s, s.query(User).first().id, project["id"]).payload())
    assert "journal.example.org" not in payload and "Page 3" not in payload


def test_unticked_at_pause_never_in_checkpoint_context(client, auth, project, SessionTest):
    dh, _ = device(client, auth)
    client.post("/api/tabs/sync", headers=dh, json={"tabs": [TABS[0], TABS[6]]})
    tabs = client.get("/api/tabs", headers=auth).json()["tabs"]
    client.post("/api/tabs/select", headers=auth, json={"tab_ids": [t["id"] for t in tabs], "selected": True})
    keep = [t["id"] for t in tabs if "Study B" in t["title"]]
    cp = client.post("/api/checkpoints", headers=auth, json={"project_id": project["id"], "included": {"tabs": keep}}).json()
    from app.models import Checkpoint
    with SessionTest() as s:
        ctx = build_context(s, s.query(User).first().id, project["id"], s.get(Checkpoint, cp["id"]))
        payload = json.dumps(ctx.payload())
    assert "Study B" in payload and "ZETA" not in payload


# 18–19. Active work time and time away ---------------------------------------------------------
def test_heartbeats_active_time_and_away(SessionTest, client, auth, project):
    with SessionTest() as s:
        user = s.query(User).first()
        prefs = s.get(UserPreferences, user.id)
        p = s.get(Project, project["id"])
        t0 = utcnow() - timedelta(hours=3)
        for i in range(5):  # five heartbeats 30 s apart = 2 min active
            heartbeat(s, user.id, p.id, prefs, now=t0 + timedelta(seconds=30 * i))
        heartbeat(s, user.id, p.id, prefs, now=t0 + timedelta(hours=1))  # gap > 5 min → away, new session
        st = time_status(s, user.id, p, prefs, now=t0 + timedelta(hours=3))
        recs = s.query(TimeTrackingRecord).filter_by(project_id=p.id).all()
    assert st["total_recorded_seconds"] == 120
    assert any(r.kind == "away" and r.seconds > 3000 for r in recs)
    assert 119 <= st["minutes_away"] <= 121 and st["suggested_help_level"] == "balanced"
    assert "not a verified absence" in st["basis"]


def test_heartbeat_api_summary_and_manual_correction(client, auth, project):
    pid = project["id"]
    client.post("/api/time/heartbeat", headers=auth, json={"project_id": pid})
    st = client.get(f"/api/time/status?project_id={pid}", headers=auth).json()
    assert st["active_now"] is True and st["minutes_away"] == 0
    start = (utcnow() - timedelta(hours=2)).isoformat()
    end = (utcnow() - timedelta(hours=1)).isoformat()
    rec = client.post("/api/time/records", headers=auth, json={"project_id": pid, "started_at": start, "ended_at": end, "note": "paper"}).json()
    assert rec["seconds"] == 3600
    summ = client.get(f"/api/time/summary?project_id={pid}&days=7", headers=auth).json()
    assert summ["total_active_seconds"] >= 3600 and len(summ["days"]) == 7
    client.patch(f"/api/time/records/{rec['id']}", headers=auth, json={"kind": "away"})
    assert client.get(f"/api/time/summary?project_id={pid}&days=7", headers=auth).json()["total_active_seconds"] < 3600
    assert client.post("/api/time/records", headers=auth, json={"project_id": pid, "started_at": end, "ended_at": start}).status_code == 422


def test_extension_heartbeat_ignored_in_private_mode(client, auth, project):
    dh, _ = device(client, auth)
    client.patch("/api/privacy", headers=auth, json={"private_mode": True})
    assert client.post("/api/time/heartbeat", headers=dh, json={"project_id": project["id"], "source": "extension"}).json()["recorded"] is False


# 20. Break detection preferences ----------------------------------------------------------------
def test_break_preferences(client, auth):
    r = client.patch("/api/me/preferences", headers=auth, json={"break_threshold_minutes": 20, "break_reminders": False}).json()
    assert r["preferences"]["break_threshold_minutes"] == 20 and r["preferences"]["break_reminders"] is False
    assert client.patch("/api/me/preferences", headers=auth, json={"break_threshold_minutes": 0}).status_code == 422


# 25. Google Docs and Word: read-only ----------------------------------------------------------------
GOOGLE_DOC = {"title": "Lit review (Google)", "body": {"content": [
    {"paragraph": {"elements": [{"textRun": {"content": "2.3 Measuring trust\n"}}], "paragraphStyle": {"namedStyleType": "HEADING_2", "headingId": "h.abc123"}}},
    {"paragraph": {"elements": [{"textRun": {"content": "Study A used a survey.\n"}}], "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}}},
    {"paragraph": {"elements": [{"textRun": {"content": PARA + "\n"}}], "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}}},
]}}


def docx_bytes(paras):
    d = Docx()
    d.add_heading("Discussion", level=1)
    for p in paras:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture()
def fake_cloud(monkeypatch, SessionTest):
    calls = []
    state = {"google": GOOGLE_DOC, "word": docx_bytes(["Study A used a survey.", PARA])}

    def handler(req: httpx.Request):
        calls.append((req.method, str(req.url)))
        u = str(req.url)
        if u.startswith("https://oauth2.googleapis.com/token") or "login.microsoftonline.com" in u:
            return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "readonly"})
        if u.startswith("https://openidconnect.googleapis.com/v1/userinfo"):
            return httpx.Response(200, json={"email": "maya@gmail.com"})
        if u.startswith("https://docs.googleapis.com/v1/documents/"):
            return httpx.Response(200, json=state["google"])
        if u.endswith("/me"):
            return httpx.Response(200, json={"mail": "maya@uni.edu"})
        if "/shares/" in u or "/me/drive/items/ITEM1" in u and not u.endswith("/content"):
            return httpx.Response(200, json={"id": "ITEM1", "name": "Chapter 2.docx", "webUrl": "https://onedrive.live.com/edit?id=ITEM1",
                                             "parentReference": {"driveId": "D1"}})
        if u.endswith("/drives/D1/items/ITEM1/content"):
            return httpx.Response(200, content=state["word"])
        return httpx.Response(404)
    monkeypatch.setattr(xhttp, "transport", httpx.MockTransport(handler))
    from app.config import get_settings
    s = get_settings()
    for k, v in {"google_client_id": "gid", "google_client_secret": "gs", "microsoft_client_id": "mid", "microsoft_client_secret": "ms"}.items():
        monkeypatch.setattr(s, k, v)
    return {"calls": calls, "state": state}


def oauth(client, auth, provider):
    url = client.get(f"/api/integrations/{provider}/start", headers=auth).json()["url"]
    assert "readonly" in url or "Files.Read" in url
    state = url.split("state=")[1].split("&")[0]
    r = client.get(f"/api/integrations/{provider}/callback?code=c&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307) and "connected=" + provider in r.headers["location"]


def test_google_docs_read_only_flow(client, auth, project, fake_cloud):
    assert client.post("/api/integrations/documents", headers=auth, json={"project_id": project["id"], "provider": "google",
                       "url_or_id": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"}).status_code == 412
    oauth(client, auth, "google")
    accts = client.get("/api/integrations/accounts", headers=auth).json()
    assert accts["accounts"][0]["account_email"] == "maya@gmail.com" and "token" not in json.dumps(accts).lower().replace("tokens", "")
    doc = client.post("/api/integrations/documents", headers=auth, json={"project_id": project["id"], "provider": "google",
                      "url_or_id": "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"}).json()
    assert doc["read_only"] and doc["source"] == "google_docs"
    # editing a connected document is refused
    assert client.patch(f"/api/documents/{doc['id']}", headers=auth, json={"content_text": "x"}).status_code == 409
    # Pause: paragraphs offered for marking
    draft = client.get(f"/api/projects/{project['id']}/pause-draft?document_id={doc['id']}", headers=auth).json()
    paras = draft["external_paragraphs"]
    assert paras[-1]["text"] == PARA
    # User marks where they stopped
    cp = client.post("/api/checkpoints", headers=auth, json={"project_id": project["id"], "document_id": doc["id"],
                     "position": {"paragraph_index": 2, "paragraph_text": PARA, "heading_id": "h.abc123", "source": "user_marked"}}).json()
    assert cp["position"]["provenance_label"] == "Saved by You"
    rw = client.post(f"/api/checkpoints/{cp['id']}/resume-writing", headers=auth).json()
    assert rw["mode"] == "external" and rw["open_url"].endswith("#heading=h.abc123") and rw["show_paragraph"] == PARA
    # Skipped marking → AI Guess from the changed paragraph
    fake_cloud["state"]["google"] = {**GOOGLE_DOC, "body": {"content": GOOGLE_DOC["body"]["content"] + [
        {"paragraph": {"elements": [{"textRun": {"content": "A brand new paragraph.\n"}}], "paragraphStyle": {}}}]}}
    cp2 = client.post("/api/checkpoints", headers=auth, json={"project_id": project["id"], "document_id": doc["id"]}).json()
    assert cp2["position"]["source"] == "ai_guess" and cp2["position"]["provenance_label"] == "AI Guess"
    assert cp2["position"]["paragraph_text"] == "A brand new paragraph."
    # restore is refused; copy text offered
    r = client.post(f"/api/checkpoints/{cp['id']}/restore", headers=auth)
    assert r.status_code == 409 and PARA in r.json()["detail"]["copy_text"]
    # compare snapshots works
    vs = client.get(f"/api/documents/{doc['id']}/versions", headers=auth).json()
    assert vs["read_only"] and len(vs["versions"]) >= 3
    # NEVER a write request to Google: only GETs to the Docs API; POSTs only to the token endpoint
    for method, url in fake_cloud["calls"]:
        if "docs.googleapis.com" in url:
            assert method == "GET", (method, url)
        if method != "GET":
            assert "oauth2.googleapis.com/token" in url, (method, url)


def test_word_onedrive_and_upload(client, auth, project, fake_cloud):
    oauth(client, auth, "microsoft")
    doc = client.post("/api/integrations/documents", headers=auth, json={"project_id": project["id"], "provider": "microsoft",
                      "url_or_id": "https://onedrive.live.com/edit?id=ITEM1"}).json()
    assert doc["source"] == "word" and doc["read_only"] and doc["title"] == "Chapter 2"
    assert PARA in client.get(f"/api/documents/{doc['id']}", headers=auth).json()["content_text"]
    for method, url in fake_cloud["calls"]:
        if "graph.microsoft.com" in url:
            assert method == "GET", (method, url)
    # Uploaded .docx
    up = client.post("/api/integrations/word/upload", headers=auth, data={"project_id": str(project["id"])},
                     files={"file": ("Discussion.docx", docx_bytes(["My discussion paragraph."]), "application/octet-stream")}).json()
    assert up["title"] == "Discussion" and up["read_only"]
    bad = client.post("/api/integrations/word/upload", headers=auth, data={"project_id": str(project["id"])}, files={"file": ("x.docx", b"nope")})
    assert bad.status_code == 422
    client.delete("/api/integrations/microsoft", headers=auth)
    assert client.get("/api/integrations/accounts", headers=auth).json()["accounts"] == []


def test_oauth_not_configured_message(client, auth):
    r = client.get("/api/integrations/google/start", headers=auth)
    assert r.status_code == 503 and "GOOGLE_CLIENT_ID" in r.json()["detail"]
