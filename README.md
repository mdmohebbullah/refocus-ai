# Re-Focus AI — Version 1

**Pick up where you left off. Capture → Review → Resume.**

Re-Focus AI helps people who write and do research get back into their work after an interruption. When you pause, it saves where you stopped, what you were thinking, and which sources you had open. When you come back, it shows you that context, with every item labelled by where it came from: **Saved by You**, **Recorded Activity**, **AI Guess**, **AI Suggestion** or **User Confirmed**. An AI guess is never shown as if it were a memory.

| Part | Technology |
|---|---|
| Web app | React 18 + TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, TipTap editor, Recharts, Lucide icons |
| API | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 in production, SQLite for local development |
| AI | OpenAI (optional). Without a key, a deterministic placeholder AI is used and labelled as such in the interface |
| Browser extension | Chrome Manifest V3 (`extension/`) |
| Documents | Built-in editor (editable). Google Docs and Word are connected **read-only** |

See `docs/ARCHITECTURE.md` for the system design and data model, and `docs/TEST_REPORT.md` for what was tested at each stage, including what could not be tested here.

---

## 1. Run it locally

You need Python 3.12 or newer and Node 20 or newer.

```bash
# API
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # the defaults work for local use
alembic upgrade head                                   # creates refocus.db (SQLite)
uvicorn app.main:app --reload --port 8000

# Web app (second terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

Open http://localhost:5173, create an account, then create a project. The Vite dev server forwards `/api` to port 8000.

### Use PostgreSQL locally (optional)

```bash
createdb refocus
# in backend/.env
DATABASE_URL=postgresql+psycopg2://YOUR_USER:YOUR_PASSWORD@localhost:5432/refocus
alembic upgrade head
```

## 2. Load the Chrome extension

1. In Re-Focus AI, open **Settings & Privacy → Browser extension & devices**, name the browser and click **Create device token**. Copy the token (it starts with `rfd_` and is shown only once).
2. In Chrome, go to `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and choose the `extension/` folder.
3. Click the Re-Focus AI icon in the toolbar. Enter the API address (`http://localhost:8000` locally, or your deployed URL) and the app address, paste the token, and click **Pair this browser**.
4. Recent history and page text are off until you turn them on in the popup. Chrome asks for permission separately for each.

The extension never sends pages with a password field, sign-in or checkout pages, browser-internal pages, or any site on your exclusion list. Turning on **Private mode**, or turning collection off for the device, stops all collection immediately. Unpairing a device (in Settings) revokes its token.

## 3. Connect the optional services

Everything works without these. Each one switches on as soon as its environment variables are set in `backend/.env` and the API is restarted.

### OpenAI (AI suggestions and voice transcription)

1. Create an API key at https://platform.openai.com/api-keys.
2. Set `OPENAI_API_KEY=sk-...` (and optionally `OPENAI_MODEL`, which defaults to `gpt-4o-mini`).
3. Restart the API. `GET /api/health` should now report `"ai_provider": "openai"`.

Only the evidence the user approved in the Pause panel is sent: their own notes, thoughts and goal, selected sources, and recorded activity they ticked. If the OpenAI call fails, the app falls back to the placeholder AI and says so. Voice clips are only uploaded if the user turns on **Allow voice clips to be uploaded** in Settings. Otherwise the browser's own speech recognition is used, or the user types.

### Google Docs (read-only)

1. In Google Cloud Console, create a project and enable the **Google Docs API** and **Google Drive API**.
2. Under **OAuth consent screen**, add these scopes:
   - `documents.readonly`
   - `drive.metadata.readonly`
   - `openid`
   - `email`
   While the app is in *Testing*, also add your test users.
3. Under **Credentials → Create credentials → OAuth client ID → Web application**, add this authorized redirect URI:
   `{PUBLIC_API_URL}/api/integrations/google/callback`
   For example: `http://localhost:8000/api/integrations/google/callback`
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then restart the API.

### Microsoft Word on OneDrive or SharePoint (read-only)

1. In the Azure portal, go to **App registrations → New registration**.
2. Choose the supported account types. `MICROSOFT_TENANT=common` allows both personal and work accounts.
3. Add a **Web** redirect URI: `{PUBLIC_API_URL}/api/integrations/microsoft/callback`
4. Under **Certificates & secrets**, create a client secret.
5. Under **API permissions**, add these delegated permissions:
   - `Files.Read.All`
   - `User.Read`
   - `offline_access`
   - `openid`
   - `email`
6. Set `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` and `MICROSOFT_TENANT`, then restart the API.

Word files can also be uploaded as `.docx` files without connecting an account.

**Read-only guarantee.** Re-Focus AI only reads these documents. It uses read-only scopes, and its code makes only `GET` requests to the Google Docs and Microsoft Graph APIs. The only `POST` requests are to the token endpoints. Tokens are stored encrypted (Fernet). Disconnecting deletes them.

## 4. Deploy

The production build is a single service: the FastAPI app serves the built React app and the API from the same origin.

### Docker Compose (PostgreSQL + app)

```bash
cp backend/.env.example backend/.env       # set SECRET_KEY, and any optional keys
docker compose up --build                  # http://localhost:8000
```

The container runs `alembic upgrade head` before it starts.

### Any container host (Render, Railway, Fly.io, Azure App Service, Cloud Run …)

1. Create a managed PostgreSQL database.
2. Deploy the `Dockerfile` in the repository root. The host provides `PORT`, and the image listens on it.
3. Set these environment variables:
   - `ENVIRONMENT=production`. The API refuses to start with a weak `SECRET_KEY`.
   - `SECRET_KEY`: generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - `TOKEN_ENCRYPTION_KEY`: recommended; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   - `DATABASE_URL=postgresql+psycopg2://…`
   - `FRONTEND_URL`, `PUBLIC_API_URL` and `CORS_ORIGINS`: all set to your public HTTPS URL.
   - Optionally the OpenAI, Google and Microsoft variables. Update their redirect URIs to the public URL.
4. Serve the app over HTTPS only.
5. Back up the database regularly. Deleted accounts remain in backups until those backups expire; this is explained to users on the Delete account screen.

### Without Docker

```bash
cd frontend && npm ci && npm run build          # creates frontend/dist
cd ../backend && pip install -r requirements.txt
alembic upgrade head
ENVIRONMENT=production uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
```

### Publishing the extension

Change the default API and app addresses in `extension/lib/api.js` to your deployed URL. Then run `cd extension && npm run package`, which creates `refocus-ai-extension.zip`, and upload the zip in the Chrome Web Store developer dashboard. You will need a privacy policy that matches the data practices described above.

## 5. Tests

```bash
cd backend && python -m pytest tests -q                       # 56 API tests, stages A–D
TEST_DATABASE_URL=postgresql+psycopg2://…/refocus_test python -m pytest tests -q   # same tests on PostgreSQL
cd frontend && npm test                                       # panel navigation unit tests
cd extension && npm test                                      # privacy filter tests

# End-to-end, in a real browser (needs: pip install playwright && playwright install chromium)
python e2e/maya_flow.py           # Scenarios 1–6 (BASE=http://127.0.0.1:5173 by default)
python e2e/stage_d_flow.py        # History, Search, Settings, sync, phone/tablet layouts, account deletion
python e2e/extension_smoke.py     # loads the real extension and pairs it (API=http://127.0.0.1:8000)
```

## 6. Project layout

```
backend/    FastAPI app (app/), Alembic migrations (alembic/), tests (tests/)
frontend/   React app — pages/, panels/ (pop-up panels with Back/Forward), components/, hooks/, state/
extension/  Chrome MV3 extension — background.js, popup/, lib/filter.js (privacy filter)
e2e/        Playwright end-to-end scripts
docs/       ARCHITECTURE.md, TEST_REPORT.md
```

## 7. Known limitations in Version 1

- Google Docs and Word are read-only by design. Re-Focus AI cannot place your cursor inside Google Docs or Word. It opens the document at the nearest heading and shows the paragraph where you stopped.
- Where you stopped in an external document is either the paragraph you marked when you paused, or an **AI Guess** based on what changed since the last snapshot. The guess is labelled as one.
- Activity is tracked only in browsers with the extension paired. Re-Focus AI does not see other apps.
- Voice input uses the browser's speech recognition where available (Chrome or Edge). Uploading audio is opt-in and needs an OpenAI key.
- Sync between devices uses polling every 20 seconds or so, not live push.
