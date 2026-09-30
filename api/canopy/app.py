from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_auth, routes_changes, routes_workspace
from .core.config import get_settings
from .core.errors import install_error_handlers
from .core.logging import RequestIdMiddleware, configure_logging
from .jobs.app import app as jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The API only *defers* jobs; it needs the queue's connection pool open.
    async with jobs.open_async():
        yield


def create_app(*, with_jobs: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="Canopy",
        description="A group chart of accounts for multi-entity Xero groups.",
        version="0.1.0",
        lifespan=lifespan if with_jobs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_base_url],
        allow_credentials=True,  # session cookie
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(routes_auth.router)
    app.include_router(routes_workspace.router)
    app.include_router(routes_changes.router)

    @app.get("/health", tags=["ops"])
    async def health():
        return {"ok": True}

    return app
