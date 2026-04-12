from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from backend.routers import items, search, tags
from pipelines.constants import REPO_ROOT


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
    except ImportError:
        pass
    yield


app = FastAPI(title="TNJIndex API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(tags.router, prefix="/api")

_images_root = REPO_ROOT / "data" / "images"
if _images_root.is_dir():
    app.mount("/media", StaticFiles(directory=str(_images_root)), name="media")

_static_root = REPO_ROOT / "backend" / "static"
if _static_root.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_static_root), html=True),
        name="frontend",
    )
