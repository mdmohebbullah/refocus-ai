"""Stage D — voice upload rules, privacy controls, export, account deletion, sync, data isolation (Features 18, 23)."""
import json

from sqlalchemy import func, select

from app.models import ActivityEvent, Checkpoint, ConnectedAccount, Project, User
from app.security import encrypt_json
from conftest import _register
from test_stage_a import pause
from test_stage_b import device, events


# 18. Voice: upload only with consent, and only when a transcription service is configured -------
def test_voice_upload_requires_consent_and_service(client, auth):
    files = {"audio": ("t.webm", b"\x1aE\xdf\xa3fake", "audio/webm")}
    r = client.post("/api/voice/transcribe", headers=auth, files=files)
    assert r.status_code == 403 and "turned off" in r.json()["detail"]
    client.patch("/api/me/preferences", headers=auth, json={"voice_upload_allowed": True})
    r = client.post("/api/voice/transcribe", headers=auth, files=files)
    assert r.status_code == 503 and "type your thought" in r.json()["detail"]


# 23. Privacy settings -----------------------------------------------------------------------
def test_privacy_patch_exclusions_and_defaults(client, auth):
    p = client.get("/api/privacy", headers=auth).json()
    assert "chase.com" in p["effective_exclusions"] and p["default_categories"] and p["deletion_notes"]
    p = client.patch("/api/privacy", headers=auth, json={"excluded_domains": ["https://www.Example.com/path"],
                                                          "removed_default_exclusions": ["chase.com"],
                                                          "history_retention_days": 7}).json()
    assert "example.com" in p["effective_exclusions"] and "chase.com" not in p["effective_exclusions"]
    assert p["history_retention_days"] == 7
    assert client.patch("/api/privacy", headers=auth, json={"history_retention_days": 0}).status_code == 422
    # a site the user excluded is dropped by ingestion
    dh, _ = device(client, auth)
    r = client.post("/api/activity/batch", headers=dh, json={"events": events([3], base="https://example.com/a")}).json()
    assert r["stored"] == 0 and r["dropped_excluded"] == 1


def test_private_mode_and_device_toggle_stop_collection(client, auth):
    dh, did = device(client, auth)
    client.patch("/api/privacy", headers=auth, json={"private_mode": True})
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([2])}).json()["collection"] == "off"
    client.patch("/api/privacy", headers=auth, json={"private_mode": False})
    client.patch(f"/api/devices/{did}", headers=auth, json={"collection_enabled": False})
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([2])}).json()["collection"] == "off"
    client.patch(f"/api/devices/{did}", headers=auth, json={"collection_enabled": True})
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([2])}).json()["stored"] == 1
    # revoking a device invalidates its token
    assert client.delete(f"/api/devices/{did}", headers=auth).status_code == 204
    assert client.post("/api/activity/batch", headers=dh, json={"events": events([1])}).status_code == 401


def test_export_contains_data_but_no_secrets(client, auth, project, SessionTest):
    pause(client, auth, project)
    dh, _ = device(client, auth)
    client.post("/api/activity/batch", headers=dh, json={"events": events([4])})
    with SessionTest() as s:
        uid = s.scalar(select(User.id).where(User.email == "maya@example.edu"))
        s.add(ConnectedAccount(user_id=uid, provider="google", account_email="maya@gmail.test",
                               scopes="documents.readonly", token_encrypted=encrypt_json({"access_token": "SECRET-ACCESS"})))
        s.commit()
    r = client.get("/api/privacy/export", headers=auth)
    assert r.status_code == 200
    blob = json.dumps(r.json())
    data = r.json()
    assert data["projects"] and data["checkpoints"] and data["activity_events"] and data["devices"]
    assert data["connected_accounts"][0]["provider"] == "google"
    for secret in ("SECRET-ACCESS", "token_hash", "token_encrypted", "password_hash", "rfd_"):
        assert secret not in blob


def test_account_delete_requires_password_and_cascades(client, auth, project, other_auth, SessionTest):
    pause(client, auth, project)
    dh, _ = device(client, auth)
    client.post("/api/activity/batch", headers=dh, json={"events": events([4])})
    assert client.post("/api/account/delete", headers=auth, json={"password": "wrong", "confirm": "DELETE"}).status_code == 403
    assert client.post("/api/account/delete", headers=auth, json={"password": "correct-horse-1", "confirm": "yes"}).status_code == 422
    r = client.post("/api/account/delete", headers=auth, json={"password": "correct-horse-1", "confirm": "DELETE"})
    assert r.status_code == 200 and r.json()["deleted"]
    assert client.get("/api/me", headers=auth).status_code == 401
    with SessionTest() as s:
        assert s.scalar(select(func.count()).select_from(Project)) == 0
        assert s.scalar(select(func.count()).select_from(Checkpoint)) == 0
        assert s.scalar(select(func.count()).select_from(ActivityEvent)) == 0
        assert s.scalar(select(func.count()).select_from(User)) == 1  # the other user is untouched
    assert client.get("/api/projects", headers=other_auth).status_code == 200


# Sync across devices -------------------------------------------------------------------------
def test_sync_status_changes_and_is_shared_across_sessions(client, auth, project):
    # a second sign-in for the same account = a second device
    login = client.post("/api/auth/login", json={"email": "maya@example.edu", "password": "correct-horse-1"}).json()
    laptop2 = {"Authorization": f"Bearer {login['access_token']}"}
    v1 = client.get("/api/sync/status", headers=auth).json()["version"]
    assert client.get("/api/sync/status", headers=laptop2).json()["version"] == v1
    tid = client.post("/api/thoughts", headers=laptop2, json={"project_id": project["id"], "thinking": "Check sample sizes"}).json()["id"]
    v2 = client.get("/api/sync/status", headers=auth).json()["version"]
    assert v2 != v1
    thoughts = client.get(f"/api/thoughts?project_id={project['id']}", headers=auth).json()
    assert any(t["id"] == tid for t in thoughts["thoughts"])
    client.patch("/api/me/preferences", headers=laptop2, json={"help_level": "detailed"})
    assert client.get("/api/me", headers=auth).json()["preferences"]["help_level"] == "detailed"
    assert client.get("/api/sync/status", headers=auth).json()["version"] != v2


# Data isolation ------------------------------------------------------------------------------
def test_users_cannot_reach_each_others_data(client, auth, project, other_auth):
    _, cp = pause(client, auth, project)
    did = project["documents"][0]["id"]
    pid = project["id"]
    for method, url in [("get", f"/api/projects/{pid}"), ("get", f"/api/documents/{did}"), ("get", f"/api/checkpoints/{cp['id']}"),
                        ("get", f"/api/projects/{pid}/resume"),
                        ("get", f"/api/documents/{did}/versions"), ("post", f"/api/checkpoints/{cp['id']}/restore"),
                        ("delete", f"/api/projects/{pid}")]:
        r = getattr(client, method)(url, headers=other_auth)
        assert r.status_code == 404, (url, r.status_code)
    assert client.get("/api/projects", headers=other_auth).json()["projects"] == []
    assert client.get(f"/api/thoughts?project_id={pid}", headers=other_auth).json()["thoughts"] == []
    s = client.get("/api/search?q=Study", headers=other_auth).json()
    assert s["results"] == [] and s["ai_inferred"] == []
    assert client.get("/api/projects", headers=auth).json()["projects"]


def test_device_token_cannot_use_account_endpoints(client, auth):
    dh, _ = device(client, auth)
    assert client.get("/api/privacy/export", headers=dh).status_code in (401, 403)
    assert client.post("/api/account/delete", headers=dh, json={"password": "correct-horse-1", "confirm": "DELETE"}).status_code in (401, 403)
    assert client.post("/api/devices", headers=dh, json={"name": "x"}).status_code in (401, 403)
    assert client.patch("/api/privacy", headers=dh, json={"excluded_domains": []}).status_code == 403
    # what the extension legitimately needs still works
    assert client.patch("/api/privacy", headers=dh, json={"private_mode": True}).status_code == 200
    assert client.get("/api/tabs", headers=dh).status_code == 200


def test_unauthenticated_requests_rejected(client):
    for url in ("/api/projects", "/api/privacy", "/api/sync/status", "/api/history"):
        assert client.get(url).status_code == 401
    _register(client, "z@example.edu", "Z")
    assert client.get("/api/projects", headers={"Authorization": "Bearer nonsense"}).status_code == 401
