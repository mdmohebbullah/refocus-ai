"""Stage D end-to-end check against the production build (API serving frontend/dist).
Covers: History, Smart Search, Settings & Privacy (pairing, exclusions, private mode, help level, shortcut editor,
export), cross-device sync between two browser sessions, mobile/tablet layouts, and account deletion."""
import json, os, re, sys, time

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:8010")
SHOTS = os.environ.get("SHOTS", "/tmp/claude-0/shots")
EMAIL = f"maya{int(time.time())}@example.edu"
PW = "correct-horse-1"
os.makedirs(SHOTS, exist_ok=True)

# Seed an account with a project, text and a checkpoint through the API (UI for this is covered by maya_flow.py).
api = httpx.Client(base_url=BASE, timeout=20)
tok = api.post("/api/auth/register", json={"email": EMAIL, "name": "Maya Chen", "password": PW}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
pid = api.post("/api/projects", headers=H, json={"name": "Literature review: trust in XAI", "goal": "Compare how Study A and Study B measured user trust"}).json()["id"]
did = api.get(f"/api/projects/{pid}", headers=H).json()["documents"][0]["id"]
text = "Study A used a self-report scale. However, Study A and Study B differed in their measurement of user trust because"
api.patch(f"/api/documents/{did}", headers=H, json={"content_text": text, "cursor_pos": len(text),
          "content_json": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}})
api.post("/api/checkpoints", headers=H, json={"project_id": pid, "document_id": did, "goal": "Compare trust measures",
         "position": {"cursor": len(text), "paragraph_index": 0, "paragraph_text": text, "source": "cursor"}})
api.post("/api/references", headers=H, json={"project_id": pid, "title": "Study B — behavioural reliance", "url": "https://journal.example.org/studyB", "why_saved": "methods"})
api.patch("/api/me/preferences", headers=H, json={"current_project_id": pid})


def sign_in(page):
    page.goto(BASE)
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PW)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("navigation", name="Main").or_(page.get_by_role("button", name="Open menu")).first).to_be_visible()


def shot(page, name):
    page.screenshot(path=f"{SHOTS}/{name}.png")


errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    sign_in(page)

    # History & Timeline
    page.get_by_role("link", name="History & Timeline").click()
    expect(page.get_by_text(re.compile("Checkpoint", re.I)).first).to_be_visible()
    shot(page, "d01_history")

    # Smart Search
    page.get_by_role("link", name="Smart Search").click()
    page.get_by_label("Search").fill("Study B source")
    page.keyboard.press("Enter")
    expect(page.get_by_text("Matches in your saved records")).to_be_visible()
    expect(page.get_by_text("Study B — behavioural reliance").first).to_be_visible()
    shot(page, "d02_search")

    # Settings: device pairing
    page.get_by_role("link", name="Settings & Privacy").click()
    expect(page.get_by_text("Website exclusion list")).to_be_visible()
    page.get_by_label("Name this browser").fill("Lab Chrome")
    page.get_by_role("button", name="Create device token").click()
    token = page.locator("code").first.inner_text()
    assert token.startswith("rfd_"), token
    expect(page.get_by_text("Lab Chrome")).to_be_visible()

    # Exclusion list + private mode
    page.get_by_label("Website to exclude").fill("https://www.mybank-example.com/login")
    page.get_by_role("button", name="Exclude", exact=True).click()
    expect(page.get_by_role("button", name="Stop excluding mybank-example.com")).to_be_visible()
    page.get_by_role("checkbox", name=re.compile("^Private mode")).click()
    expect(page.locator("header").get_by_text("Private mode")).to_be_visible()
    dev = {"Authorization": f"Bearer {token}"}
    r = api.post("/api/activity/batch", headers=dev, json={"events": [{"title": "x", "url": "https://journal.example.org/a", "occurred_at": "2026-11-15T10:00:00Z"}]}).json()
    assert r["collection"] == "off", r
    page.get_by_role("checkbox", name=re.compile("^Private mode")).click()
    expect(page.locator("header").get_by_text("Private mode")).to_have_count(0)

    # Help level + shortcut editor
    page.get_by_label("AI help level").select_option("detailed")
    expect(page.get_by_label("AI help level")).to_have_value("detailed")
    page.get_by_role("button", name="Change shortcut for Save thought").click()
    page.keyboard.press("Alt+Shift+Y")
    expect(page.get_by_role("button", name="Change shortcut for Save thought")).to_have_text("Alt+Shift+Y")
    shot(page, "d03_settings")

    # Export
    with page.expect_download() as dl:
        page.get_by_role("button", name="Export all my data (JSON)").click()
    data = json.loads(open(dl.value.path()).read())
    assert data["projects"] and data["devices"] and "token_hash" not in json.dumps(data)

    # Cross-device sync: a second session on a "phone" sees a thought saved on the laptop
    phone_ctx = b.new_context(**p.devices["iPhone 13"])
    phone = phone_ctx.new_page()
    phone.on("pageerror", lambda e: errors.append(str(e)))
    sign_in(phone)
    api.post("/api/thoughts", headers=H, json={"project_id": pid, "thinking": "Synced from the laptop: check sample sizes"})
    phone.goto(f"{BASE}/thoughts")
    expect(phone.get_by_text("Synced from the laptop: check sample sizes")).to_be_visible()
    assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll on phone"
    shot(phone, "d04_phone_thoughts")
    for path, name in [("/", "d05_phone_dashboard"), ("/resume", "d06_phone_resume"), ("/settings", "d07_phone_settings")]:
        phone.goto(BASE + path)
        phone.wait_for_load_state("networkidle")
        assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), f"horizontal scroll on {path}"
        shot(phone, name)
    phone.get_by_role("button", name="Open menu").click()
    expect(phone.get_by_role("dialog", name="Menu")).to_be_visible()
    phone_ctx.close()

    tablet = b.new_context(viewport={"width": 820, "height": 1180}).new_page()
    sign_in(tablet)
    tablet.goto(BASE + "/resume")
    tablet.wait_for_load_state("networkidle")
    assert tablet.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    shot(tablet, "d08_tablet_resume")

    # Account deletion
    page.goto(BASE + "/settings")
    page.get_by_label("Password").fill(PW)
    page.get_by_label("Type DELETE to confirm").fill("DELETE")
    page.get_by_role("button", name="Delete account").click()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    assert api.get("/api/me", headers=H).status_code == 401
    b.close()

real = [e for e in errors if "fonts.googleapis" not in e and "Failed to load resource" not in e]
print("CONSOLE ERRORS:", real)
print("STAGE D E2E: PASS" if not real else "STAGE D E2E: FAIL")
sys.exit(1 if real else 0)
