# 🌳 Canopy — Multi-Entity Command Centre for Xero

**One change, propagated correctly across every Xero organisation in the group.**
An AI proposes structured mappings and explains its reasoning; a human approves once;
deterministic, schema-validated code writes to Xero — never the AI.

Built for the Xero **"Rise of the Builder"** hackathon, grounded in eight stakeholder
interviews plus a technical deep-dive with the group's BI lead. Groups running 20+ Xero
entities make the same change (a new expense code, a product, a supplier, a tracking
category) by hand, org by org — slow, and error-prone in ways that fail an audit. Canopy
does it in one reviewed batch.

---

## The core idea

```
                        ┌─ snapshot each entity's live chart / tax / contacts / items
 one source change ─────┤
 + target entities      └─ LLM maps it to THAT entity's data → one Proposal per entity
                                   │  (action, mapped_payload, confidence, reasoning, needs_human)
                                   ▼
                         batched approval table  ──►  human approves / edits / excludes once
                                   │
                                   ▼
                         deterministic execution: validate payload → write with an explicit
                         per-request Xero-Tenant-Id → record full request/response audit
```

**The rule enforced everywhere in code:** the LLM only *proposes* structured JSON. It may
never invent an account code, tax type, or tracking id — if nothing in the target org fits,
it must refuse (`needs_human`) rather than guess. Only deterministic, Pydantic-validated
code writes, and only after human approval. Tenant IDs are explicit per request, never
cached globally. No money movement — items, accounts, contacts, and tracking categories only.

### Deterministic guards (the LLM is proposed *and* checked)

The AI is capable but not trusted blindly. After every proposal, deterministic backstops run:

- **Referenced-code guard** — any account code in a mapped payload that doesn't exist in the
  target org's chart forces `needs_human` instead of a guaranteed write failure.
- **Account collision guard** — Xero requires unique account Code *and* Name; a clash is
  flagged pre-write rather than failing at the API.
- **Option coercion** — tracking Options are normalised whether the model emits `["Sales"]`
  or Xero's native `[{"Name":"Sales"}]`.

These have each caught the model being confidently wrong in live runs against real orgs.

---

## Features

**Multi-entity propagation** — proven end-to-end against real Xero trial organisations
(written, then read back to confirm), for all four change types:

| Change type | Live-proven | Test |
|---|:---:|:---:|
| Item (sales/purchase account + tax mapping) | ✅ | ✅ |
| Account code (with Code/Name collision guard) | ✅ | ✅ |
| Contact (dedup link-vs-create) | ✅ | ✅ |
| Tracking category (+ options) | ✅ | ✅ |

**Universal file ingest** — upload *any* CSV/JSON/xlsx export (`POST /ingest`), the LLM
infers what the file *is* — no per-source connector code — and normalises rows to per-entity
manual-journal proposals in the same approval table. Unmappable columns are flagged
`needs_human`; nothing is written. Demo payloads: a messy Sortly-style stock count and a
Roller-style revenue export (`seed/fixtures/`).

**Entity health with cross-org drift detection** — each org's header pill flags account
codes that exist in most orgs in the group but are missing there, straight from the cached
snapshots (`GET /entities` → `health.drift`).

**An upstream fix to Xero's official MCP server** — see
[Toolkit contribution](#toolkit-contribution).

**50 backend tests pass** (credential-free — the LLM and Xero client are injected seams).
Deep-dives live in `docs/architecture.md` and `docs/pitch.md`.

---

## Architecture

| Layer | Stack |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy · SQLite |
| Frontend | Next.js 16 · React 19 · Tailwind v4 (App Router) |
| AI | Azure AI Foundry via the OpenAI-compatible SDK (`gpt-5.4-mini`), structured output via forced tool-calling |
| Xero | One standard OAuth 2.0 auth-code app connected to N orgs; explicit `Xero-Tenant-Id` per request; OAuth token Fernet-encrypted at rest, auto-refreshed |

```
backend/
  app/
    main.py            FastAPI app + routers
    config.py          pydantic-settings (.env)
    db.py, models.py   entities, tokens, snapshots, runs, proposals, write_results
    xero/
      auth.py          consent URL, callback, encrypted token store, refresh
      client.py        Xero API wrapper — explicit tenant_id per call
      ratelimit.py     per-tenant limiter
    snapshots.py       per-entity chart/tax/contacts/items/tracking cache (TTL)
    engines/
      mapping.py       per-entity propagation engine + deterministic guards
      contracts.py     Pydantic payload/proposal schemas
      llm.py           structured-completion seam (Azure Foundry / OpenAI)
    execution.py       validate → write → record audit
    routers/           auth · entities · changes · runs · demo
  tests/               golden mapping tests, contract validation, execution, guards
frontend/
  src/app, src/components, src/lib/api.ts   batched approval UI
docker-compose.yml     full stack (backend :8000 + frontend :3000)
```

---

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | liveness |
| `GET`  | `/auth/xero/connect` → `/auth/xero/callback` | OAuth consent + token storage, syncs connected orgs |
| `GET`  | `/entities` | connected orgs (+ snapshot age) |
| `GET`  | `/entities/{id}/organisation` | live read proving the connection |
| `POST` | `/changes` | `{change_type, payload, target_entity_ids}` → fans out mapping, returns proposals |
| `POST` | `/ingest` | multipart file (CSV/JSON/xlsx) → schema inference → per-entity journal proposals |
| `GET`  | `/runs`, `/runs/{id}` | run history / detail |
| `POST` | `/runs/{id}/approve` | per-row include/exclude/edit → execute → per-row results |
| `POST` | `/demo/seed`, `/demo/seed-ingest` | dev-only offline demo runs (gated by `DEMO_MODE`) |

---

## Running it

### Prerequisites
- Python 3.12+, Node 22+
- A Xero developer app (auth-code flow, redirect `http://localhost:8000/auth/xero/callback`)
  and one or more UK trial organisations
- An Azure AI Foundry (or any OpenAI-compatible) endpoint + key

### Configure
```bash
cp backend/.env.example backend/.env
# fill in XERO_CLIENT_ID / XERO_CLIENT_SECRET, the LLM endpoint + key,
# and a CANOPY_FERNET_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Local (recommended for development)
```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev            # http://localhost:3000
```

> On Windows, run plain `uvicorn` (no `--reload`) — the file-watcher's parent/worker
> process model can keep serving stale code after edits. Hard-restart after changes.

### Docker (deployment artifact)
```bash
docker compose up --build      # backend :8000, frontend :3000, persistent SQLite volume
```
Secrets are read from `backend/.env` at runtime and are never baked into an image. Set
`DEMO_MODE=false` for a real-org deployment so the offline demo-seed path is disabled.

### Tests
```bash
cd backend && python -m pytest -q     # 50 passing, no credentials required
```

---

## Design principles (from the stakeholder research)

- **Batched, approve-first** — one review for the whole fan-out, not per-org approval fatigue.
- **Per-row confidence, reasoning, and refusal-to-guess** — *"'It's the computer what did it'
  isn't a defence"*: every write is explainable and audited.
- **Human-in-the-loop is mandatory** — `needs_human` is a first-class blocking state, not an error.
- **No money movement; full run-history audit** of every request and response.

---

## Toolkit contribution

While building Canopy we found that Xero's official MCP server
([`XeroAPI/xero-mcp-server`](https://github.com/XeroAPI/xero-mcp-server)) hardcodes the
**first** tenant returned by the connections endpoint — in both bearer-token and
client-credentials modes. With one app or token authorised for several organisations, every
server instance silently operates on org #1 with no way to target another.

We fixed it: an optional `XERO_TENANT_ID` environment variable honoured by both auth modes,
failing loudly (with the list of available tenant IDs) if it doesn't match an authorised
connection rather than silently falling back. Non-breaking when unset, covered by unit tests.

**Upstream PR:** [XeroAPI/xero-mcp-server#208](https://github.com/XeroAPI/xero-mcp-server/pull/208)

---

*Canopy is a hackathon build. Live secrets belong only in the gitignored `backend/.env`.*
