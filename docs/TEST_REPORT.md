# Re-Focus AI v1 — Test Report

Run on 15 November 2026 in a Linux build environment (Python 3.13, Node 20, Chromium via Playwright, PostgreSQL 16).

## Summary

| Suite | Result |
|---|---|
| Backend API tests, SQLite | **56 / 56 pass** |
| Backend API tests, PostgreSQL 16 (`TEST_DATABASE_URL`) | **56 / 56 pass** |
| Alembic migration on PostgreSQL: `upgrade head` + `alembic check` | Pass. The schema matches the models; no drift |
| Frontend unit tests (Vitest) | **4 / 4 pass** |
| TypeScript (`tsc --noEmit`) and production build (`vite build`) | Clean |
| Extension privacy-filter tests (`node --test`) | **5 / 5 pass** |
| E2E, Scenarios 1–6 (`e2e/maya_flow.py`) on the production build | Pass, 0 console errors |
| E2E, Stage D (`e2e/stage_d_flow.py`), production build + PostgreSQL | Pass, 0 console errors |
| E2E, real extension loaded in Chromium (`e2e/extension_smoke.py`) | Pass |

## Stage A — core experience (Features 1, 2, 7–10, 12–17, panel navigation 5A)

22 API tests:
- Accounts: register, login and me; short passwords rejected.
- Projects: create, read, update and delete; search and categories.
- Documents: saving and automatic versioning.
- Pause and checkpoints:
  - Pause draft and checkpoint creation.
  - Unticking the goal or position excludes them.
  - An unfinished thought keeps its exact wording and links back to its position.
  - Thoughts are saved with the checkpoint.
- Future-self question: adapts to the position; can be skipped.
- Resume card:
  - Separates facts from guesses.
  - Resume writing restores the cursor.
  - With no checkpoint, the card says the context is incomplete.
- Why? panel:
  - At most three clues, all citing real evidence.
  - Clues that point to evidence which doesn't exist are dropped.
  - The heading says "1 clue" when there is only one.
- Help level: the user's preference overrides the time-away suggestion; the time-away table is checked.
- Review: Partly requires the user's own text and then becomes User Confirmed. A rejected guess is never shown as information again. Accept works.
- Data isolation: another user can't see anything.

4 frontend tests cover the panel stack:
- Back and Forward, disabled at the ends.
- Opening a new panel clears Forward history.
- Each panel keeps its own state.
- Typed text is restored after Back/Forward.

E2E (`maya_flow.py`) goes through the whole flow in a browser:
- Register, create a project and type in the editor.
- Pause: fill in the unfinished thought, answer the future-self question, save the checkpoint.
- Resume card; switch help level to Balanced.
- Why? shows "Based on N clue(s)".
- Partly: type a correction, go Back then Forward (the text is restored), Use my step, then it shows as User Confirmed.
- Resume writing highlights the paragraph in the editor.
- The dashboard shows Resume previous work.

## Stage B — browser and documents (Features 3, 4, 11, read-only Google Docs and Word)

16 API tests:
- Devices: pairing and revocation.
- Tabs:
  - Banking, health and sign-in tabs are never stored.
  - Select all, deselect, and exclude a site.
  - Approved sites are remembered.
  - Page text is only stored with the content permission.
- Last 60 minutes: filters checked.
- Collection: private mode and the per-device toggle both stop it.
- AI context:
  - Excluded and unselected items never reach the AI payload.
  - Items unticked at pause never enter the checkpoint context.
- Time tracking:
  - Heartbeats count active time; gaps count as away.
  - Summary API and manual corrections.
  - Extension heartbeats are ignored in private mode.
- Break-reminder preferences.
- Google Docs and Word:
  - Google Docs read-only flow, using a mocked Google API.
  - Word on OneDrive, and `.docx` upload.
  - A clear message when OAuth isn't configured.
  - Tests check that only `GET` requests reach the document APIs.

5 extension tests cover the privacy filter.

E2E (`extension_smoke.py`) loads the real unpacked MV3 extension in Chromium and pairs it. Tabs sync to the API, and a `/login` tab is filtered out before it is sent.

## Stage C — history and research (Features 5B, 6, 19–22)

9 API tests:
- Checkpoint timeline: Older/Newer; restoring is non-destructive (current text is kept as a version first).
- Versions: compare and restore.
- History:
  - Filters tell work apart from browser activity.
  - History older than the retention period is removed.
- Notes and references are kept separate, with links between them.
- Smart Search:
  - The three example questions return results.
  - Search respects private mode and exclusions.
- Tasks and pins carry into the Resume card.
- Shortcuts can be changed, and browser shortcuts are refused.

## Stage D — voice, privacy, sync and delivery (Features 18, 23)

9 API tests:
- Voice upload needs consent (403 without it) and a configured service (503 without it).
- Privacy settings:
  - Full URLs entered as exclusions are reduced to their domain.
  - Default exclusions can be removed.
  - Out-of-range retention values are rejected.
- Private mode and the per-device toggle stop collection; a revoked device token gets 401.
- Data export:
  - Includes projects, checkpoints, activity, devices and connected accounts.
  - Contains **no** tokens, token hashes or password hashes. This was checked with a real encrypted token in the database.
- Account deletion:
  - Needs the password and the word "DELETE".
  - Deletes everything the account owns; other users' data is untouched.
- Sync: two sessions on the same account see the same sync version, and a change on one is visible on the other.
- Data isolation: every project, document, checkpoint, resume and restore endpoint returns 404 to another user, and search returns nothing of theirs.
- **Device tokens are limited.** A browser-extension token can't:
  - export data or delete the account;
  - pair new devices or manage connected accounts;
  - clear history;
  - change privacy settings other than private mode.
- Unauthenticated and invalid tokens are rejected.

E2E (`stage_d_flow.py`) runs against the production build served by FastAPI, with PostgreSQL:
- History & Timeline; Smart Search finds a saved reference.
- Settings & Privacy:
  - Creating a device token.
  - Adding an exclusion.
  - Private mode on: the header shows it, and the device's uploads are refused. Then off again.
  - Changing the help level.
  - Recording a new shortcut (Alt+Shift+Y).
  - Exporting data; the JSON has no secrets.
- Cross-device sync: a second, phone-sized session (iPhone 13 emulation) sees a thought added from the laptop.
- Layouts:
  - No horizontal scrolling on the phone for Dashboard, Thoughts, Resume and Settings.
  - The phone menu opens.
  - Tablet layout (820×1180).
- Deleting the account signs the user out, and the old session token stops working.

## Problems found and fixed during testing

- **Security, Stage D.** A device token could call account-level endpoints, including export and delete-account. These now require a signed-in user (`account_user`), and the extension can only change private mode and its own device settings.
- **Security, hardening.** The frontend file server now refuses paths outside `frontend/dist`. Production mode refuses to start with the default or a short `SECRET_KEY`.
- **Phone layout.** The header cut off the Pause button on phones. The button now reads "Pause", the project selector shrinks, and the logo is hidden.
- **Privacy settings.** URLs typed into the exclusion list were stored as typed. They are now reduced to the domain.
- Earlier stages (details in the commit history):
  - The pause panel took the cursor position at the wrong moment.
  - Retention purging didn't run before reading history.
  - Guesses could end with a double full stop.
  - The future-self question ignored the paragraph where you stopped.

## Not tested here (needs real accounts or hardware)

| Item | Why | How to verify |
|---|---|---|
| Real OpenAI responses and Whisper transcription | No API key in the build environment. The placeholder provider and the fallback path are tested, and the OpenAI provider's JSON parsing and clue checks run through the same code | Set `OPENAI_API_KEY`, then pause and resume; `/api/health` should show `openai` |
| Real Google and Microsoft sign-in (OAuth) | No OAuth client credentials. The whole flow is tested against mocked endpoints (`httpx.MockTransport`) | Follow README §3 and connect an account in Settings |
| Docker image build | No Docker daemon in the build environment. Each Dockerfile step was run by hand: `npm run build`, `pip install`, `alembic upgrade head`, then uvicorn serving `dist` on PostgreSQL | `docker compose up --build` |
| Chrome Web Store packaging and review | Needs a developer account | README §4 |
| Microphone speech recognition | Headless browsers have no microphone. The UI falls back to typing | Use Chrome on a real device |
| Real phones and tablets | Checked with emulated sizes only | Open the deployed URL on a phone |
