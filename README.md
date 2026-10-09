# 🌳 Canopy — a group chart of accounts for Xero

Groups that run many Xero organisations end up with charts of accounts that drift apart:
the same account under different codes, codes that exist in some orgs but not others,
acquired companies that arrive with their own numbering. Xero manages one organisation
at a time, so keeping them consistent is manual.

Canopy connects to every org in a group (read-only), mirrors each chart of accounts, and
maps every org's accounts to **one group standard** — without forcing the orgs to be
identical. Deterministic matching handles the obvious cases, an AI suggests the rest, and
a person confirms every mapping. The result is a live gap matrix (which group accounts
each org is missing) and an exportable mapping that consolidation tools can use.

> **Status:** v2. Milestone 1 (read-only mapping), Milestone 2 (approved changes to
> accounts) and Milestone 2b (tracking categories) are built. The original hackathon build
> lives on `master`.

---

## How it works

1. **Sign up with Xero** — identity only (`openid profile email`).
2. **Connect organisations** — an admin grants `accounting.settings.read`. Connections
   stay read-only unless write access is deliberately granted later (step 7).
3. **Sync** — each org's chart is mirrored: full sync on connect and nightly (catches
   deletions), incremental sync (`If-Modified-Since`) in between.
4. **Group standard** — seed it from one org's chart or import a CSV, then edit.
5. **Mapping** — for each org account:
   - exact code + name → high confidence
   - same name, different code → a coding-scheme difference
   - same code, different name → flagged, never trusted automatically
   - everything else → one batched AI call per org (account metadata only), checked by
     guards that reject invented codes and cross-class mappings (revenue ↛ expense)

   Every result is a *suggestion* until a person confirms, rejects or reassigns it.
   Regenerating suggestions never overwrites a human decision.
6. **Gaps & export** — a group account is a gap in an org when none of that org's live
   accounts is confirmed against it. Confirmed mappings export as CSV.
7. **Controlled changes** (opt-in per workspace) — create a missing account, rename or edit
   one, or archive one, across orgs:
   - a preparer proposes a change; **a different person approves it**. A group with a
     single approver can have the owner allow self-approval, but only while nobody else
     can approve, only for changes that bring an org into line with the group standard
     (never an archive or a code change), and only with a note. Each self-approved change
     waits in a review queue until someone else reviews it;
   - deterministic checks run before submission and again just before writing — code and
     name unique (archived accounts included), tax type valid for that org and class, no
     system accounts, write access granted — and a failed check means nothing is written;
   - each org's write carries an `Idempotency-Key`, so retries never double-apply; each
     result stores the account before and after, and a created account closes its gap;
   - write access (`accounting.settings`) is granted per org, only once changes are on;
     `XERO_WRITES_ENABLED=false` stops every write server-wide.
8. **Tracking categories** — the same standard, mapping, gaps and controlled changes for
   tracking categories and their options (e.g. Region: London, Bristol). The standard
   holds at most two active categories, because Xero allows two per org. Matching is by
   name; changes create a missing category with its options, add an option, rename, or
   archive, and the checks enforce Xero's limits (two active / four total categories,
   unique names including archived ones). Archiving is never self-approved.
9. **Connections** — each organisation shows whether it's connected, needs reconnecting
   (Canopy lost access; its data is kept but flagged as stale and changes pause) or was
   disconnected. Disconnecting drops the connection in Xero immediately, revokes the
   Xero sign-in once none of its organisations remain, and keeps the data 30 days so a
   reconnect restores it (or removes it straight away, for offboarding). A nightly check
   catches organisations removed on Xero's side and cleans up unused connections.

## Architecture

| | |
|---|---|
| API | Python 3.13 · FastAPI · async SQLAlchemy 2 · psycopg 3 |
| Database | Postgres 16 · Alembic migrations · **row-level security** for tenant isolation |
| Jobs | procrastinate (Postgres-backed queue — no Redis); per-tenant locks |
| Web | Next.js 16 · React 19 · Tailwind 4 · types generated from the API's OpenAPI schema |
| AI | Provider-agnostic structured-output seam (Azure AI Foundry / OpenAI-compatible) |

Security model, in short:

- **Tenant isolation is enforced by Postgres.** The app connects as a role that owns no
  tables; every transaction binds `app.workspace_id` / `app.user_id`, and RLS policies
  filter every tenant table on them. A test fails if a new table ships without RLS.
- **Sessions** are server-side (only a SHA-256 of the cookie token is stored) with a CSRF
  token on every mutating request. OAuth uses state, nonce and PKCE; id_tokens are
  verified against Xero's JWKS.
- **Xero tokens** are encrypted at rest (MultiFernet, rotatable keys) and refreshed under
  a Postgres advisory lock, so concurrent workers never spend a rotated refresh token twice.
- **Rate limits** come from Xero's own `X-*Limit-Remaining` headers, persisted per tenant;
  long `Retry-After`s reschedule the job instead of blocking a worker.
- **Audit log** is append-only for the app role (no UPDATE/DELETE grant).

More detail: [`docs/architecture.md`](docs/architecture.md).

```
api/          FastAPI app + worker (package `canopy`), Alembic migrations, tests
web/          Next.js app
docker/       Postgres init (roles, test database)
docs/         architecture; hackathon/ holds the original hackathon collateral
```

## Running it locally

Prerequisites: Docker, Python 3.13, Node 22, and a Xero app (standard auth-code flow)
with redirect URI `http://localhost:8000/auth/xero/callback`.

```bash
cp api/.env.example api/.env
# fill in XERO_CLIENT_ID / XERO_CLIENT_SECRET, TOKEN_ENCRYPTION_KEYS and the LLM settings

docker compose up --build        # db, migrate, api :8000, worker, web :3000
```

Or run the API and web on the host against the containerised database:

```bash
docker compose up -d db
cd api && python -m venv .venv && .venv/Scripts/activate   # Windows; source .venv/bin/activate elsewhere
pip install -e ".[dev]" && alembic upgrade head
python -m canopy api            # and, in another terminal: python -m canopy worker

cd web && npm install && npm run dev
```

## Tests and checks

```bash
docker compose up -d db
cd api && pytest -q && ruff check canopy tests migrations
cd web && npm run typecheck && npm run lint && npm run build
```

API tests run against a real Postgres (`canopy_test`) as the same role the app uses, so
isolation, grants and SQL behave exactly as in production. After changing API response
shapes, regenerate the web types:

```bash
python -m canopy openapi > ../web/openapi.json   # from api/
npm run gen:api                                    # from web/
```

CI (`.github/workflows/ci.yml`) runs all of the above and fails if the schema or the
generated types are out of date.

---

*Built from research with a multi-entity group's finance team. Live secrets belong only in
the gitignored `api/.env`.*
