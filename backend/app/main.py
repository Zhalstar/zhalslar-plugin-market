"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, market, oauth, plugins, users
from .config import get_settings
from .database import Base, SessionLocal, engine
from .market import seed_market

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables and import the legacy seed once.

    Args:
        app: FastAPI application.

    Yields:
        Control to the running application.
    """
    del app
    settings.storage.directory.mkdir(parents=True, exist_ok=True)
    settings.storage.packages_directory.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_market(db)
    yield


app = FastAPI(
    title=settings.app.name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.middleware("http")
async def same_origin_mutations(request: Request, call_next):
    """Reject cross-origin cookie-authenticated mutations.

    Args:
        request: Current request.
        call_next: Downstream ASGI handler.

    Returns:
        Downstream or rejection response.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        allowed = {item.rstrip("/") for item in settings.server.cors_origins}
        if origin and origin.rstrip("/") not in allowed:
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
    return await call_next(request)


@app.get("/api/v1/health", tags=["System"])
def health() -> dict[str, str]:
    """Return a lightweight deployment health response.

    Returns:
        Service health object.
    """
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(oauth.router, prefix="/api/v1")
app.include_router(plugins.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(market.router)
app.mount(
    settings.storage.public_path,
    StaticFiles(directory=settings.storage.directory, check_dir=False),
    name="plugin-assets",
)
