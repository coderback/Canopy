from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import auth, entities, runs

app = FastAPI(
    title="Canopy — Multi-Entity Command Centre",
    description=(
        "One change, propagated correctly across every Xero organisation in the "
        "group. Claude proposes structured mappings; deterministic validated code "
        "writes — only after one batched human approval."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(entities.router)
app.include_router(runs.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"ok": True}
