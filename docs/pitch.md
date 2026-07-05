# Canopy — Three-Minute Pitch Script

> Xero "Rise of the Builder" · 4–5 July 2026 · Encode Hub
> Targets: Bounty 01 (Productivity Powerhouse) + Bounty 02 (Vibe Integrator).
> Rule of the room: say **"eight interviews plus a technical deep-dive with their BI lead"** — not nine.

## 0:00–0:25 — The problem, with authority

"AirHop runs **20-plus entities in Xero**. We did **eight interviews with their finance team, plus a technical deep-dive with their BI lead**. The #1 structural pain, in their Senior Management Accountant Claire Hiscock's own words: *'If we wanted to set up a new expense code, you've just got to do that in every single entity — so for us that's like 20-odd entities.'* Every change — a contact, an item, an account code — re-keyed org by org, one browser window at a time. Canopy is the command centre that fixes that."

## 0:25–0:50 — Warm-up (it works across orgs)

*Live: add a new supplier contact once.*

"One form. Canopy fans it out to all three connected orgs, dedupes against each org's existing contacts — 'Acme Corp' vs 'Acme Corporation Ltd' — and queues one batched approval. Approve once. Done. That alone kills the re-keying."

## 0:50–1:40 — The intelligence (the winning moment)

*Live: push a new catalogue item.*

"Here's the part a rigid integration can't do. Org A maps cleanly — high confidence. Org B's chart of accounts is different: there is no account `200`, so Claude maps **`200 Sales` → `201 Trading Income`** and shows its reasoning. Org C has no plausible income account at all — so it **refuses to guess** and flags the row for a human.

That refusal is deliberate. AirHop's Management Accountant Anita Chakraborty told us: *'"It's the computer what did it" isn't a defence.'* So every row shows its reasoning and its confidence, and the AI never writes anything — it only proposes. Deterministic, schema-validated code does the writing, only after a human approves.

And the expense-code ask itself? *Live: propagate a new expense code.* There's no MCP tool and no SDK sugar for creating accounts — we go straight to the raw Accounting API, `PUT /Accounts`, per tenant. Claire's literal #1 request, first-class."

## 1:40–2:25 — The universal translator (Bounty 02 beat)

*Live: upload the messy Sortly-style stock CSV.*

"AirHop's stock counts live in Sortly; group revenue lives in Roller. Neither talks to Xero — their team downloads, Excels, and re-keys journals by hand. Their Management Accountant Niro called the Sortly chain 'fully automatable'; Callum reconciles Roller revenue against Xero **daily, by hand**.

Canopy has **no Sortly connector and no Roller connector**. You drop in *any* export — messy headers, mixed formats, a missing value — and Claude works out what the file *is*, maps rows to per-entity manual journals against each org's live chart of accounts, and emits proposals into the same approval table. One column it can't map? It flags it and writes nothing. That's the bounty's 'universal translator for business data' — literally."

## 2:25–2:45 — Approve once, audit forever

*Live: glance at the flagged row, fix inline, hit Approve & propagate; per-entity results fill in; open run history.*

"One button, batched — because their Finance Director Tim Mclure warned us about approval fatigue: approve, approve, approve until you stop reading. High-confidence rows come pre-checked; flagged rows block until a human has actually looked. And every run is written to history with the full request and response — the audit trail their BI lead Charles Win built himself internally, productionised."

## 2:45–3:00 — The frame (close)

"Under the hood: one OAuth app across all orgs, tenant ID explicit on every single request — never cached globally, per Xero's own guidance. Per-tenant rate limiting, idempotent writes, no money movement by design. And while building it we found that **Xero's official MCP server hardcodes the first tenant** — multi-org tokens always hit org one — so **we fixed it and opened an upstream PR**. Canopy doesn't just use the toolkit. It improved it."

---

## Q&A ammunition

- **"Why not one Custom Connection per entity?"** Custom Connections are £5/month *per org*, AU/NZ/UK/US only, and trial orgs can't buy them. One standard OAuth app supports 25 tenants uncertified; routing is the `xero-tenant-id` header per request.
- **"What stops the AI writing something wrong?"** It can't write at all. Claude emits structured JSON proposals (forced tool calling); a Pydantic-validated deterministic layer executes only approved rows. Failure paths: unmappable file → refusal, zero writes; network death mid-fan-out → partial results recorded and retriable.
- **"Rate limits?"** 60/min and 5,000/day **per tenant**, so fan-out across tenants parallelises safely; Canopy still runs a per-tenant limiter with 429 retry/backoff.
- **"Why is PO-to-Bill not in the demo?"** Scoped and consciously cut to keep the two flagships demo-frozen. The design is on record: bills created as DRAFT only, PO status never touched — because Xero's native copy-to-bill auto-marking POs as BILLED is the AP team's #1 pain (Tamika: *"we can't find that purchase order. We've then got to go find the purchase order separately, unbill it, match it..."*).
- **"Is this what users asked for?"** Tim Mclure, verbatim: *"The invoice comes in. The system reads it and says: here's the invoice, this is what I think we should do. Is that right? The human approves it. That's what we want."*

## Judging-criteria map

| Criterion | Weight | Where it lands |
|---|---|---|
| Real problem + strong Xero use | 50% | Eight-interview research base; kills one-entity-at-a-time re-keying; contacts/items/accounts/tracking/journals used deeply |
| API integration | 30% | OAuth multi-tenant, granular scopes, snapshot reads feeding mapping, raw `PUT Accounts`, manual journals; upstream MCP-server PR |
| Production-ready architecture | 20% | Propose/approve/execute separation, Pydantic validation, per-tenant rate limits, idempotency, encrypted tokens, full run audit |
