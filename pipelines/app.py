"""
Local dev search UI (FastAPI + static /media).

  uv run python -m pipelines.app

Binds 127.0.0.1:8000 by default.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pipelines.constants import REPO_ROOT
from pipelines.search import search
from scrapers.db import get_conn

app = FastAPI(title="TNJIndex Search Dev")

_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
_images_root = REPO_ROOT / "data" / "images"
if _images_root.is_dir():
    app.mount("/media", StaticFiles(directory=str(_images_root)), name="media")


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass


@app.on_event("startup")
def _startup() -> None:
    _load_dotenv()


def _media_url(rel: str | None) -> str | None:
    """DB paths like data/images/thumbnails/x.jpg → /media/thumbnails/x.jpg."""
    if not rel or not str(rel).strip():
        return None
    s = str(rel).replace("\\", "/")
    prefix = "data/images/"
    if s.startswith(prefix):
        return "/media/" + s[len(prefix) :].lstrip("/")
    if s.startswith("images/"):
        return "/media/" + s[len("images/") :].lstrip("/")
    return "/media/" + s.lstrip("/")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(
        "index.html",
        {"request": request},
    )


@app.get("/api/search")
async def api_search(q: str = "", k: int = 10) -> JSONResponse:
    k = max(1, min(int(k), 50))
    q = (q or "").strip()
    if not q:
        return JSONResponse({"results": [], "query": q, "k": k})

    conn = get_conn()
    try:
        rows = search(q, k=k, conn=conn)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        conn.close()

    payload = []
    for r in rows:
        thumb = _media_url(r.get("thumbnail_path"))
        orig = _media_url(r.get("image_path"))
        payload.append(
            {
                **r,
                "thumbnail_url": thumb,
                "image_url": orig,
            }
        )
    return JSONResponse({"results": payload, "query": q, "k": k})


def main() -> None:
    _load_dotenv()
    import uvicorn

    host = os.environ.get("TNJ_DEV_HOST", "127.0.0.1")
    port = int(os.environ.get("TNJ_DEV_PORT", "8000"))
    uvicorn.run(
        "pipelines.app:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
