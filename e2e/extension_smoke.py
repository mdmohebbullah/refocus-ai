"""Load the real MV3 extension in Chromium, pair it with a device token, and verify tab sync + privacy filtering."""
import json, os, sys, time, tempfile, urllib.request
from playwright.sync_api import sync_playwright

API = os.environ.get("API", "http://127.0.0.1:8000")
EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extension"))

def req(path, body=None, token=None, method=None):
    r = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"),
                               headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.loads(urllib.request.urlopen(r).read() or b"null")

email = f"ext{int(time.time())}@example.edu"
tok = req("/api/auth/register", {"email": email, "name": "Ext", "password": "correct-horse-1"})["access_token"]
proj = req("/api/projects", {"name": "Extension test"}, tok)
dev = req("/api/devices", {"name": "Test Chrome"}, tok)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=True, channel="chromium",
        args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
    ext_id = sw.url.split("/")[2]
    print("extension loaded:", ext_id)
    # Open some pages: one normal, one sensitive (sign-in), one excluded domain.
    pg = ctx.new_page(); pg.goto("data:text/html,<title>Study B methods</title>hello")
    page2 = ctx.new_page(); page2.goto(API + "/api/health")          # http page, normal
    page3 = ctx.new_page(); page3.goto(API + "/login?x=1")           # sensitive path → never sent
    popup = ctx.new_page(); popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")
    popup.fill("#apiBase", API); popup.fill("#token", dev["token"]); popup.click("#pairBtn")
    popup.wait_for_selector("#main:not([hidden])", timeout=15000)
    time.sleep(2)
    tabs = req("/api/tabs", token=tok)["tabs"]
    urls = [t["url"] for t in tabs]
    print("server tabs:", urls)
    assert any(u and u.endswith("/api/health") for u in urls), "normal tab should sync"
    assert not any(u and "/login" in u for u in urls), "sign-in page must never be sent"
    assert not any(u and u.startswith("chrome-extension") for u in urls), "internal pages must never be sent"
    assert not any(u and u.startswith("data:") for u in urls)
    # Select a tab from the popup and check the server
    popup.reload(); popup.wait_for_selector("#tabs input", timeout=10000)
    popup.locator("#tabs input").first.check(); time.sleep(1)
    assert any(t["selected"] for t in req("/api/tabs", token=tok)["tabs"]), "selection from popup should persist"
    print("popup status:", popup.inner_text("#status"))
    popup.screenshot(path="/tmp/claude-0/shots/ext_popup.png")
    ctx.close()
print("EXTENSION SMOKE OK")
