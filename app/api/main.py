import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import auth, roles
from app.config import get_settings
from app.db.session import engine
from app.org.seed import seed_roles

log = logging.getLogger("aiorg")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    with Session(engine()) as db:
        n = seed_roles(db, settings.roles_dir)
    log.info("seeded/updated %d roles", n)
    yield


app = FastAPI(title="AI Org", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(roles.router)


@app.get("/api/health", tags=["ops"])
def health() -> dict[str, str]:
    with engine().connect() as c:
        c.execute(text("select 1"))
    return {"status": "ok"}


def mount_spa() -> None:
    dist = Path(get_settings().static_dir)
    if not (dist / "index.html").exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


mount_spa()
