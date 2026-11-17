"""End-to-end walk through Maya's workflow in a real browser (Stage A scenarios 1–6)."""
import os, sys, time, re
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("BASE", "http://127.0.0.1:5173")
SHOTS = os.environ.get("SHOTS", "/tmp/claude-0/shots")
EMAIL = f"maya{int(time.time())}@example.edu"

def shot(page, name):
    page.screenshot(path=f"{SHOTS}/{name}.png", full_page=False)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(BASE)
    page.get_by_role("button", name="Create an account").click()
    page.get_by_label("Name").fill("Maya Chen")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill("correct-horse-1")
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_text("Create a project for the writing")).to_be_visible()
    shot(page, "01_empty_dashboard")

    # Project
    page.get_by_role("button", name="Start new project").first.click() if page.get_by_role("button", name="Start new project").count() else page.get_by_role("button", name="New project").first.click()
    page.get_by_label("Project name").fill("Literature review: trust in explainable AI")
    page.get_by_label("Goal").fill("Compare how Study A and Study B measured user trust")
    page.get_by_role("button", name="Create project").click()
    page.get_by_role("link", name=re.compile("Main draft")).click()

    # Write in the editor
    ed = page.locator(".ProseMirror")
    ed.click()
    page.keyboard.type("Explainable AI is often assumed to increase user trust, yet findings remain mixed. ")
    page.keyboard.press("Enter")
    page.keyboard.type("Study A measured trust with a seven-item self-report scale. Study B recorded how often operators accepted the model's advice.")
    page.keyboard.press("Enter")
    page.keyboard.type("However, Study A and Study B differed in their measurement of user trust because")
    expect(page.get_by_role("status").filter(has_text="Saved")).to_be_visible(timeout=8000)
    shot(page, "02_editor")

    # Scenario 1 + 2: Pause, untick, unfinished thought, future-self question, save
    page.get_by_role("button", name="Pause Session").click()
    expect(page.get_by_text("Exact writing position")).to_be_visible()
    page.get_by_label("What were you thinking?").fill("Self-report and observed reliance may disagree.")
    page.get_by_label("What information is missing?").fill("A study that measured both.")
    page.get_by_label("What were you planning to do next?").fill("Explain why the two measures can diverge.")
    page.get_by_label("Your answer").fill("B is behavioral, A is a survey.")
    shot(page, "03_pause_panel")
    page.get_by_role("button", name="Save checkpoint").click()
    expect(page.get_by_text("Checkpoint saved")).to_be_visible()

    # Scenario 3: Resume card
    page.get_by_role("link", name="Resume Workspace").click()
    expect(page.get_by_text("What you were trying to do")).to_be_visible()
    shot(page, "04_resume_card")

    # Scenario 5: help level → Balanced
    page.get_by_role("button", name="Change help level").click()
    page.get_by_text("Balanced", exact=True).click()
    page.get_by_role("button", name="Apply").click()
    expect(page.get_by_text("Suggested next step")).to_be_visible()
    shot(page, "05_balanced")

    # Scenario 4: Why? → open source → Back keeps panel
    page.get_by_role("button", name="Why?").last.click()
    expect(page.get_by_text(re.compile(r"Based on \d clue"))).to_be_visible()
    shot(page, "06_why")

    # Scenario 6: Partly → own step → Back/Forward restores typed text
    page.get_by_role("button", name="Partly").last.click()
    page.get_by_label("What is needed instead?").fill("Check the discussion paragraph first.")
    page.get_by_role("button", name="Back to previous panel").click()
    page.get_by_role("button", name="Forward to next panel").click()
    expect(page.get_by_label("What is needed instead?")).to_have_value("Check the discussion paragraph first.")
    shot(page, "07_partly")
    page.get_by_role("button", name="Use my step").click()
    expect(page.get_by_text("User Confirmed").first).to_be_visible()
    page.get_by_role("button", name="Close panel").click()
    shot(page, "08_user_confirmed")

    # Resume writing: cursor + highlight
    page.get_by_role("button", name="Resume writing").click()
    expect(page.locator(".rf-resume-mark")).to_be_visible(timeout=5000)
    shot(page, "09_resumed_editor")

    page.get_by_role("link", name="Dashboard").click()
    expect(page.get_by_role("button", name="Resume previous work")).to_be_visible()
    shot(page, "10_dashboard")
    b.close()
    real = [e for e in errors if "fonts.googleapis" not in e and "Failed to load resource" not in e]
    print("CONSOLE ERRORS:", real)
    sys.exit(1 if real else 0)
