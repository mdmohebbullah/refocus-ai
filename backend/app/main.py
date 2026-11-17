"""Re-Focus AI API — Capture → Review → Resume."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import (account, auth, browser, checkpoints, dashboard, history, integrations, projects, research, resume,
                      thoughts, worktime)

logging.basicConfig(level=logging.INFO)
settings = get_settings()
if settings.environment == "production" and (settings.secret_key.startswith("change-me") or len(settings.secret_key) < 32):
    raise RuntimeError("Set SECRET_KEY to a long random value before running in production (see .env.example).")

app = FastAPI(title="Re-Focus AI", version="1.0.0", description="Pick Up Where You Left Off. Capture → Review → Resume.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

for r in (auth, projects, checkpoints, thoughts, resume, dashboard, browser, worktime, research, history, account, integrations):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_provider": "openai" if settings.ai_enabled else "placeholder", "version": app.version}


# In production the built frontend is served by the API (single deployable service).
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(404, "Not found")
        f = (_dist / path).resolve()
        inside = f.is_relative_to(_dist.resolve())  # never serve files outside the built frontend
        return FileResponse(f if path and inside and f.is_file() else _dist / "index.html")
