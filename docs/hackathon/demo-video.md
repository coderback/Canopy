# Backup Demo Video — Shot List

Record a clean end-to-end run as insurance against live API flakes on stage. Mirror the pitch beats (`docs/pitch.md`) so the video can substitute for any live segment mid-pitch.

## Before recording

- [ ] Backend up (`uvicorn app.main:app` from `backend/`), frontend up (`npm run dev` from `frontend/`), all three orgs connected (`GET /entities` shows 3).
- [ ] Reset to a clean demo state: `POST /demo/seed` (requires `DEMO_MODE=true` in `.env`) — this is the reset lever **between takes**.
- [ ] Warm the snapshots (open the home page; entity health bar shows all orgs green/amber, no stale caches mid-take).
- [ ] Fixtures within reach: `seed/fixtures/sortly_stock_count.csv` (messy one) — not the cleaned variants.
- [ ] Browser zoom ~125%, hide bookmarks bar, close extra tabs. 1080p minimum, cursor visible.

## Shots (match pitch timing)

| # | Shot | What must be visible | Pitch beat |
|---|------|----------------------|-----------|
| 1 | Home page with entity health bar | 3 org names, health dots | 0:00 problem framing |
| 2 | New contact form → submit | one form, 3 target entities selected | 0:25 warm-up |
| 3 | Approval table for the contact run | one row per entity, dedup reasoning ("Acme Corp" vs "Acme Corporation Ltd"), confidence chips | 0:25 warm-up |
| 4 | New item form → submit → approval table | org A high-confidence; **org B row showing `200 Sales` → `201 Trading Income` with reasoning expanded**; **org C row flagged `needs_human` / refusal** | 0:50 intelligence |
| 5 | New account-code change → approval table | the expense-code row per entity (raw `PUT Accounts` beat) | 1:20 Claire's ask |
| 6 | Ingest upload of messy Sortly CSV | file drop, schema-inference result, per-entity manual-journal proposals, **one flagged/unmappable column with no write** | 1:40 universal translator |
| 7 | Fix flagged row inline → Approve & propagate | per-entity results filling in (success ticks) | 2:25 approve once |
| 8 | Run history | full run list + one run opened showing request/response audit | 2:35 audit |
| 9 | (Cutaway) Xero UI in two orgs | the propagated item/account visible inside Xero itself — org B under `201 Trading Income` | proof beat |
| 10 | (Cutaway) the upstream MCP PR page | title + diff of `XERO_TENANT_ID` override | 2:45 close |

## Rules

- One take per shot is fine; stitch later. Re-seed (`POST /demo/seed`) between full-run retakes so contact/item names don't collide.
- Never show `.env`, tokens, or the Xero client secret on screen.
- Keep a full uncut end-to-end run (shots 2→8 continuous) as the primary fallback; the per-shot clips are for mid-pitch splicing.
- After recording, verify in Xero (direct API read or UI) that the demo objects exist per org — then optionally archive/void them so the next live run is clean.
