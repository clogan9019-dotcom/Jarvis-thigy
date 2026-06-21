"""Frontend/HUD serving helpers for the local backend."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
APP_DIST_DIR = REPO_ROOT / "app" / "dist"
APP_DIST_INDEX = APP_DIST_DIR / "index.html"
PREVIEW_INDEX = REPO_ROOT / "index.html"


def register_frontend(app: FastAPI) -> None:
    """Serve the J.A.R.V.I.S HUD from the backend base URL when available."""
    assets_dir = APP_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def root():
        if APP_DIST_INDEX.exists():
            return FileResponse(APP_DIST_INDEX)
        if PREVIEW_INDEX.exists():
            return FileResponse(PREVIEW_INDEX)

        return {
            "ok": True,
            "name": "J.A.R.V.I.S Backend",
            "mode": "LOCAL_ONLY",
            "message": "Backend is running, but no HUD build was found. Run `npm run build` in app/ or open /docs.",
            "endpoints": {
                "health": "/health",
                "docs": "/docs",
                "chat": "/chat",
                "websocket": "/ws",
                "memory": "/memory",
            },
        }
