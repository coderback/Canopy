from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import auth, changes, demo, entities, ingest, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Canopy — Multi-Entity Command Centre",
    description=(
        "One change, propagated correctly across every Xero organisation in the "
        "group. An LLM proposes structured mappings; deterministic validated code "
        "writes — only after one batched human approval."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(entities.router)
app.include_router(changes.router)
app.include_router(ingest.router)
app.include_router(runs.router)
app.include_router(demo.router)


@app.get("/health")
def health():
    return {"ok": True}
