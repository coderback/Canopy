# Multi-Entity Command Centre — Hackathon Build Spec
### Xero "Rise of the Builder" Hackathon · 4–5 July 2026 · Encode Hub, Shoreditch
**Primary track:** Bounty 02 — The Vibe Integrator · **Secondary fit:** Bounty 01 — Productivity Powerhouse

Working codename: **Chorus** (one instruction, sung correctly by many organisations). Rename freely.

---

## 1. The one-sentence pitch

> Make a change once — a contact, a catalogue item, a tracking category — and an AI layer propagates it correctly across every Xero organisation in the group, *mapping* the differences between non-identical entities and asking for a single batched approval before it writes anything.

This is deliberately **Bounty 02, not just connectivity**: the value isn't "we connected N orgs," it's "the AI interprets and maps data across orgs that don't line up, and replaces brittle if-this-then-that logic with adaptive, context-aware syncing" — which is the bounty's stated intent almost verbatim.

---

## 2. Why this problem (research grounding)

From the 10 June AirHop stakeholder interviews (9 sessions). Multi-entity operations was the single most-repeated structural pain:

- **Claire (Senior Management Accountant):** 20+ entities; Xero shows one at a time with no cross-entity bulk actions; any change (e.g. a new expense code) must be replicated manually in every single entity.
- **Emily (AP Manager):** users open separate browser windows per entity; contacts cannot be centrally pushed and must be entered individually in each org.
- **Tim (Finance Director):** Xero is siloed by entity; plugins only see one entity at a time.
- **Charles (BI Lead):** already built an internal JS/AppRunner tool that bulk-syncs the *product catalogue* across entities — but only the catalogue, and it relies entirely on his expertise.

**Two findings shape the design, not just the choice:**

1. **Approval is non-negotiable but fatigue is real.** Every interviewee (Anna, Claire, Emily, Niro, Anita, Tim) independently demanded human-in-the-loop / approve-first, with zero appetite for autonomous money movement. Tim *separately* flagged approval fatigue (endless approve/approve prompts) as its own problem. → The design answer is a **single batched approval surface**, not per-action prompts.
2. **Context-blindness is the stated fear.** Claire and Anita both worry AI lacks the business context to know an output is wrong-in-context even when it looks right. → The mapping layer must **show its reasoning and confidence per row**, and **refuse to guess** when it can't map cleanly.

You can say in the pitch: *"We interviewed nine finance professionals across a 20-entity group before writing a line of code."* Almost no other team can say that — it directly feeds the 50% "real problem" score.

---

## 3. What the official Xero toolkit actually gives you (verified)

This is what makes the build feasible in a weekend and keeps you on Xero's paved road.

### Native MCP Server tools you'll use (no custom API code needed)
| Action | MCP tool | Maps to research pain |
|---|---|---|
| Read an org's chart of accounts | `list-accounts` | Needed for mapping |
| Read tax rates | `list-tax-rates` | Needed for mapping |
| Read existing contacts (dedup) | `list-contacts` | Emily |
| Read catalogue items | `list-items` | Charles |
| Read org identity | `list-organisation-details` | Entity labelling |
| **Push a contact** | `create-contact` / `update-contact` | **Emily** (contacts can't be centrally pushed) |
| **Push a catalogue item** | `create-item` / `update-item` | **Charles** (generalises his internal tool) |
| Push tracking category/option | `create-tracking-category` / `create-tracking-option` | Cross-entity structure |

### The honest gap
- **There is no `create-account` MCP tool.** Propagating a new *expense/account code* (Claire's literal example) is **not** in the toolkit — it needs the raw Accounting API `Accounts` endpoint (which does support POST/PUT) or the `xero-node` SDK. → This is a **stretch goal**, not the flagship.
- No `create-tax-rate` either (only `list-tax-rates`).

### Auth — multi-org is a supported mode (this is the unlock)
The MCP server has two auth modes:
- **Custom Connection** — one client-id/secret per org. Recommended for MCP clients. Single-org.
- **Bearer Token** — explicitly "the better choice to support multiple Xero accounts at runtime."

The **Xero CLI** is even more on-the-nose: PKCE browser login, no client secret, **multiple orgs via named profiles** (`xero contacts list --profile client-a`), `--json` output for scripting.

**Architecture decision (most robust for a weekend): one connection per entity.**
Each entity = one Custom Connection = one MCP server instance (or one CLI profile). The orchestrator holds a registry and fans out. This is bulletproof because **each connection only ever sees its own org** — which structurally enforces Xero's own security rule ("treat `xero-tenant-id` as dynamic per request, never cache globally, isolate per tenant"). Tenant isolation falls out of the architecture for free. Mention this in the architecture pitch — it's a 20%-criterion win.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js UI                                                   │
│  • Change-entry form  • Batched approval table  • Run history │
└───────────────▲───────────────────────────┬──────────────────┘
                │ approve/edit/reject        │ submit change
                │                            ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI Orchestrator (Python)                                 │
│  1. Resolve target entities                                    │
│  2. For each entity → call Mapping Engine                      │
│  3. Assemble fan-out PLAN (N entities × mapped payload)        │
│  4. On approval → fan out writes, collect per-entity results   │
└───────┬──────────────────────────────────────────┬────────────┘
        │ reason/map                                │ execute (per entity)
        ▼                                           ▼
┌────────────────────┐              ┌───────────────────────────────┐
│ Mapping Engine      │              │ Execution Layer               │
│ (Claude Sonnet)     │              │ One MCP instance / CLI profile│
│ • contact dedup     │              │ per entity (Custom Connection)│
│ • account mapping   │              │   entity-A ─▶ Xero org A      │
│ • gap detection     │              │   entity-B ─▶ Xero org B      │
│ • confidence + why  │              │   entity-C ─▶ Xero org C      │
└────────────────────┘              └───────────────────────────────┘
```

### Layers
1. **Connection registry** — config/env mapping `entity_name → {client_id, client_secret}` (or CLI profile name). 2–3 entities for the demo.
2. **Execution layer** — per-entity MCP server instance (run via `npx @xeroapi/xero-mcp-server`) or CLI profile. Orchestrator calls the one scoped to the target org.
3. **Orchestrator (FastAPI)** — receives a change request, resolves targets, drives the mapping engine, builds the plan, fans out writes on approval, records run history.
4. **Mapping Engine (Claude)** — the differentiator. See §5.
5. **Approval UI (Next.js)** — the whole fan-out as one surface. See §6.
6. **Run history** — SQLite table of every fan-out (who, what, which entities, mapped payloads, outcomes). A nod to Charles's DynamoDB run-history pattern — cite it as "production-grade auditability."

### Stack (all your existing stack)
- **Backend:** Python + FastAPI
- **Reasoning:** Claude — Sonnet for the per-entity mapping calls, optionally Opus for an orchestration/review pass (mirrors AirHop's "John Diamond" model strategy: Sonnet sufficient, Opus for review).
- **Xero execution:** Xero MCP server (Node, `npx`), one instance per Custom Connection; CLI profiles as fallback.
- **Frontend:** Next.js — two screens only (form + approval table).
- **Persistence:** SQLite (run history); in-memory state for the live session.

---

## 5. The Mapping Engine — where you win Bounty 02

This is the "AI replaces brittle integration logic" core. For each target entity, Claude does what a rigid script can't:

- **Contact dedup / matching.** Is "Acme Corp" (source) the same as "Acme Corporation Ltd" already in entity B? Fuzzy match against `list-contacts`; propose link vs create-new with confidence.
- **Account-code mapping.** A catalogue item references sales account `200 – Sales`. Entity B's `list-accounts` has no `200` but has `201 – Trading Income`. Claude maps it and flags the confidence. **This is the demo's intelligence moment** — items carry account/tax references that differ per org, so pushing an item *requires* reasoning, unlike a self-contained contact.
- **Tax-type mapping.** Source `OUTPUT2` vs target's available tax types; map or flag.
- **Gap detection / refusal.** Entity C has no plausible matching account → **do not guess**; flag the row for human input. This directly answers Claire's and Anita's "AI lacks context" fear and is a *feature to highlight*, not a limitation to hide.

Engine output per entity (structured JSON):
```json
{
  "entity": "AirHop Guildford Ltd",
  "action": "create-item",
  "mapped_payload": { "...": "valid for THIS org" },
  "confidence": 0.92,
  "reasoning": "Mapped source account '200 Sales' → '201 Trading Income' (closest income account).",
  "needs_human": false
}
```

Prompt design: feed Claude (a) the source change, (b) the target entity's accounts/tax-rates/contacts pulled live via the `list-*` tools, and (c) a strict instruction to emit valid payloads or set `needs_human: true`. Keep the system prompt as the product — same lesson as your other builds.

---

## 6. Batched approval UX — solving the unanimous + the fatigue finding

One screen. One decision surface. Not N prompts.

- **Single table**, one row per (entity × action). Columns: target entity · proposed action · mapped payload (expandable) · confidence · one-line AI reasoning · status.
- **Grouped by confidence:** high-confidence rows pre-checked; `needs_human` / low-confidence rows visually flagged and **require a glance** before the batch can run.
- **One "Approve & propagate" button** for the whole fan-out. Per-row edit or exclude available.
- **After execution:** the same table fills with per-entity success/failure, written to run history.

Pitch line: *"Every accountant we interviewed demanded approve-first — but the Finance Director warned us about approval fatigue. So approval is batched, ranked by confidence, and the AI only interrupts you for the rows it genuinely can't resolve."* That sentence ties research → design → demo and is worth rehearsing.

---

## 7. Scope fences (protect the weekend)

**IN (the gradeable core):**
- 2–3 connected demo orgs via per-entity connections
- **Contact propagation** — the warm-up (works obviously, no mapping needed)
- **Item propagation with account/tax mapping** — the flagship intelligence moment
- Mapping engine with confidence + reasoning + gap-refusal
- Batched approval surface
- Run history

**STRETCH (only if ahead by Sunday morning):**
- **Account/expense-code propagation** (Claire's literal ask) — needs raw `Accounts` endpoint, not MCP. Build only if core is solid.
- **PO-to-bill as a piped action** — run an invoice→PO matching engine, then fan the resulting bill across entities. This is where PO-to-Bill becomes a feature of this platform rather than a rival project. **Fully scoped in §7.5 — do not improvise it; either execute that plan or skip it.**
- Tracking-category propagation.

**OUT (deliberately, and say so):**
- Payments, payroll, anything that moves money. Frame as a **principled choice**: the research was unanimous that no one wants autonomous money movement, so the system is scoped to non-monetary configuration/master-data changes by design. Turning a constraint into a stated design principle reads as maturity to judges.

---

## 7.5 Scoped stretch — PO-to-Bill matching (only if core is green by Sunday midday)

**Entry condition (be honest with yourself):** do not start this unless the entire §7 core is *done and rehearsable* — multi-org contact + item propagation, mapping engine, batched approval, run history — by ~Sunday 12:00. If the core isn't solid, a half-built PO feature actively hurts the demo. This section exists so that *if* you're ahead, you execute a plan rather than improvise under pressure.

### What it adds to the story
A second, harder reasoning capability piped through the *same* approval surface: take a messy supplier invoice, match it to an open purchase order, reconstruct the line items, and produce a coded bill — then (optionally) fan that bill across entities. It pushes you from Bounty 02 (integration) into also touching Bounty 01 (productivity), and lets you say "the platform isn't just config sync — it runs intelligent AP actions too."

### The honest technical reality (why this is a stretch, not a bolt-on)
- **POs are not in the MCP toolkit.** No purchase-order tool exists. You read/match POs against the **raw Accounting API `PurchaseOrders` endpoint** (or the `xero-node` SDK), outside the MCP path you use for everything else.
- **Bills *are* creatable.** A bill is an **ACCPAY invoice** — so the write side reuses `create-invoice` (type `ACCPAY`) via the MCP server you already have. Only the *read + match* half is bespoke.
- **It's a second reasoning engine**, distinct from the cross-entity mapping engine. Budget for that — it's genuinely separate logic, which is exactly why it's fenced as a stretch.

### Minimum viable version (single org — build this first)
Keep it to one organisation. The cross-entity fan-out is a stretch-on-the-stretch.

1. **Inputs.** A sample supplier invoice (PDF or structured JSON — use structured to save OCR time; OCR is a rabbit hole, skip it) and the open POs for that org pulled from the `PurchaseOrders` endpoint.
2. **Matching engine (Claude Sonnet).** Given the invoice + list of open POs, identify the most likely matching PO and explain why. Handle the realistic mess: invoice total ≠ PO total (partial delivery), reordered/renamed line items, multi-line invoices. Emit a confidence + reasoning, same shape as the mapping engine.
3. **Line-item reconstruction.** Produce the bill's line items (description, quantity, unit amount, account code, tax type) from the matched PO + invoice. Reuse the §5 account/tax mapping logic so codes are valid for the org.
4. **Reuse the §6 approval surface.** The proposed bill becomes one more row type in the batched approval table — proposed action `create-bill (ACCPAY)`, with confidence, reasoning, `needs_human` on a weak match. **No new UI.** This is the key efficiency: it rides the rails you already built.
5. **Writeback.** On approval, `create-invoice` with `type: ACCPAY` via the MCP server.

### Engine output (mirror the §5 contract so it slots straight into the table)
```json
{
  "action": "create-bill",
  "matched_po": "PO-0042",
  "match_confidence": 0.88,
  "reasoning": "Invoice total £1,180 vs PO £1,200 — 2 of 3 lines delivered; matched on supplier + line descriptions.",
  "mapped_payload": { "type": "ACCPAY", "lineItems": ["..."] },
  "needs_human": false
}
```

### Stretch-on-the-stretch (only if PO single-org also lands)
Fan the approved bill across entities via the existing propagation engine — e.g. a shared-services invoice that recharges across sites. This is the full convergence of both ideas, but treat it as a bonus, not a target.

### Demo adjustment if PO makes it in
Add a ~30s beat after the §9 intelligence moment: "And the same approval surface runs AP actions — here's a messy supplier invoice matched to its PO, line items reconstructed, one approval to post the bill." Keep the cross-entity mapping as the headline; PO is the encore, not the lead.

### What to cut if PO runs long
If you start PO and it overruns, **abandon it and revert to the frozen core** — do not let it eat rehearsal time. The §7 core wins the track on its own; PO is upside only.

---


**Saturday**
- *AM — Foundations.* Stand up 2–3 Custom Connections against demo orgs. Get one MCP instance per org responding to `list-organisation-details` and `list-accounts`. **This is the make-or-break hour — do it first.** Confirm with a mentor you can provision multiple demo companies.
- *Midday — Read path.* Orchestrator can pull accounts/tax-rates/contacts/items from each entity.
- *PM — Write path, single entity.* `create-contact` then `create-item` into one org via the orchestrator. Prove a round-trip.
- *Evening — Fan-out.* Same write across 2–3 orgs. Hardcode payloads for now (no mapping yet). End the day with multi-org writes working.

**Sunday**
- *AM — Mapping engine.* Wire Claude in: contact dedup + item account/tax mapping + confidence + gap-refusal. This is the intelligence; protect time for it.
- *Midday — Approval UI.* The batched table; approve → fan out → results.
- *Early PM — Run history + polish.* Persist runs; tidy the two screens; seed demo data that *forces* a non-trivial mapping (an org whose accounts deliberately don't match).
- *Mid PM — Freeze & rehearse.* Stop building. Run the 3-min demo 5+ times. Prepare for the failure case (network/API flake) with a recorded backup clip.
- *Stretch slots only if green:* account-code propagation, or the **PO-to-bill matching** action per §7.5 (single-org first; only start if the core is rehearsable by ~midday). Abandon and revert to the frozen core if it overruns.

---

## 9. Three-minute demo script

- **0:00–0:30 — The problem, with authority.** "AirHop runs 20+ entities in Xero. We interviewed nine of their finance team. The #1 structural pain: every change — a new contact, a price update — has to be re-keyed in every single org, one browser window at a time."
- **0:30–1:15 — Warm-up (it works across orgs).** Add a new supplier contact once. Show it propose-and-write to all three orgs. One approval. Done. "That alone kills the re-keying."
- **1:15–2:15 — The intelligence (the winning moment).** Push a new catalogue item. Show the approval table: org A maps cleanly (high confidence); org B's chart of accounts differs, so the AI **maps `200 Sales` → `201 Trading Income`** and shows its reasoning; org C has no matching account, so the AI **refuses to guess and flags it for you.** "This is the part a rigid integration can't do — and it's exactly what our interviewees feared AI would get wrong, so we made it show its work and stop when unsure."
- **2:15–2:45 — Approve once.** Glance at the flagged row, fix it inline, hit Approve & propagate. Watch per-entity success fill in. Show run history.
- **2:45–3:00 — The frame.** "Built on Xero's own MCP server and AI toolkit. One connection per org, so tenant isolation is structural. Approve-first, batched to avoid approval fatigue — straight from the research. No autonomous money movement, by design."

---

## 10. Judging-criteria map

| Criterion | Weight | How this scores |
|---|---|---|
| Xero connection (real problem + strong Xero use) | 50% | Nine-interview research base; solves Xero's native one-entity-at-a-time limitation; uses contacts/items/accounts/tax/tracking deeply |
| API integration (Accounting API use) | 30% | MCP server tools for reads + writes across orgs; raw Accounts endpoint for the stretch; live chart-of-accounts reads feeding the mapping |
| Architecture (reliable, production-ready) | 20% | One-connection-per-entity = structural tenant isolation; batched approval = controlled writes; run history = auditability; built on official toolkit, not hand-rolled |

---

## 11. Risks & mitigations

- **Multi-org provisioning (highest risk).** You need 2–3 connected demo companies. *Mitigation:* confirm with a Xero mentor on Saturday morning, before building anything else. The one-connection-per-entity model needs each org as its own Custom Connection.
- **Tenant routing inside a single MCP instance is unverified.** *Mitigation:* the one-instance-per-entity design sidesteps it entirely — don't rely on a single instance switching tenants.
- **Account-code propagation isn't in the toolkit.** *Mitigation:* it's already scoped as a stretch on the raw API; the flagship (contacts + items) needs only native MCP tools.
- **Mapping engine over-reaches and writes a bad payload.** *Mitigation:* the whole point of batched approval + `needs_human` refusal; nothing writes without the human pressing the button.
- **Live API flakes on stage.** *Mitigation:* record a clean run Sunday afternoon as a backup; never demo on first-try live without a fallback.

---

## 12. Open actions before/at the event
- [ ] Confirm you can provision 2–3 Xero **demo companies** (mentor, Saturday AM).
- [ ] Confirm **Custom Connection** availability/cost for the hackathon vs Web-app + demo company (mentor).
- [ ] Decide MCP-instance-per-org vs CLI-profile-per-org (both work; MCP scores better on the "uses the AI toolkit" narrative).
- [ ] Seed one demo org with a deliberately mismatched chart of accounts so the mapping moment is real, not staged.
- [ ] *(PO stretch only)* Prepare one sample supplier invoice as structured JSON + at least one open PO in a demo org, so §7.5 can start instantly if the core finishes early. Verify the `PurchaseOrders` endpoint is reachable on your connection type.
