# Interview Synthesis — Pain Points, Ideas & Key Themes

Compiled from 8 stakeholder interviews conducted on **10 June 2026**. All notes derived from recorded transcripts. Charles Win (BI Lead) excluded per request.

---

## 👥 Interviewees

| Name | Role | Time |
| --- | --- | --- |
| Tamika Humes | Accounts Payable Assistant | 12:00 |
| Anna Rogolska | Accounts Payable Assistant | 12:15 |
| Claire Hiscock | Senior Management Accountant | 12:30 |
| Callum Pursall | Finance Assistant (Revenue & Reconciliation) | 12:45 |
| Tim Mclure | Finance Director, UK & Ireland | 13:00 |
| Emily Shellard | Accounts Payable Manager | 14:00 |
| Niro Udawaththage | Management Accountant | 14:15 |
| Anita Chakraborty | Management Accountant | 14:30 |

---

## 🔴 Pain Points

### 1. PO-to-Bill Workflow Broken by a Xero Update

**Who:** Tamika, Anna, Emily

This was the most consistently mentioned operational frustration across the AP team. A Xero update changed the behaviour when copying a purchase order to a bill: the system now **auto-marks the PO as billed** the moment it is copied, which causes it to disappear from ApprovalMax as an available PO. The team must then go back into ApprovalMax, manually find the PO, unbill it, re-match the bill, and re-mark it as billed — a multi-step workaround for what used to be a single action.

Anna added that the same update removed the ability to pull PO line items directly into ApprovalMax. For invoices with 10+ lines or messily formatted supplier PDFs, this forces tedious manual copy-and-paste cross-checking. Tamika's workaround is now to skip copying entirely and create every bill from scratch manually, which she described as significantly slower.

Emily noted this may be a side effect of using ApprovalMax as an external integration — if they were processing purely in Xero the auto-billing logic might make sense — but the effect on their workflow is more work, not less.

> *"It automatically bills the purchase order so then when we push it through to ApprovalMax we can't find that purchase order. We've then got to go find the purchase order separately, unbill it, match it and then do it that way."* — Tamika
> 

---

### 2. Xero Cannot Manage Multiple Entities at Once

**Who:** Claire, Emily, Tim, Anita

AirHop currently operates **20+ Xero entities**. Xero is entirely siloed — users can only view and act on one entity at a time, and there are no bulk cross-entity operations. Practical consequences raised across multiple interviews:

- Adding a new expense code must be repeated manually in every single entity
- Contacts (suppliers, customers) cannot be centrally pushed across entities — must be entered individually
- To work across two entities simultaneously, staff must open different browsers (Chrome + Safari)
- Cash balance consolidation across entities is done entirely in Excel because Xero has no multi-entity view
- When acquiring new companies, migrating them to Xero as quickly as possible is standard practice but labour-intensive

Charles has built a workaround portal that syncs product catalogue updates across all entities, but this solution is entirely dependent on Charles's knowledge. Tim noted AirHop will likely need to move to a group-level unified platform eventually, but is holding off given complexity and cost.

> *"If we had to change, if we wanted to set up a new expense code, you've just got to do that in every single entity — so for us that's like 20 odd entities."* — Claire
> 

---

### 3. Bank Reconciliation Auto-Matching is Unreliable

**Who:** Callum, Emily, Anita

Xero's AI reconciliation suggestions create as many problems as they solve. Three separate interviewees described versions of the same risk: the system matches based on amount and partial reference, leading to incorrect automatic matches that staff either miss or accept without checking.

- Callum described a case where Xero matched an incoming payment to a years-old invoice with the same amount and no reference, and it was silently reconciled before he noticed.
- Emily flagged that PLEO (an expense card system) transactions appear in reconciliation suggestions for all bank accounts, causing accidental cross-matches with unrelated invoices.
- Anita noted that staff tend to click through reconciliation suggestions without checking them — particularly dangerous because they look correct on the surface but may be contextually wrong.

Callum said he wants more reconciliation automation but currently has low confidence in the tooling. He described the ideal as a system that uses **historical transaction patterns** to suggest matches intelligently, rather than just amount-matching.

> *"There's so many different points where just like someone doing something slightly wrong or just overlooking something can lead to confusion."* — Callum
> 

---

### 4. No Workload or Activity Reporting for AP Managers

**Who:** Emily

Emily returned from leave to find she had no easy way to see who on her team had processed what invoices during her absence. Xero has no native workload distribution report. To find out who posted a specific invoice, a manager must open each bill individually and scroll to the audit trail at the bottom.

This creates two separate problems: managers cannot track team workload to balance capacity, and when errors appear, identifying who made them is time-consuming. Emily described this as a clear missing feature she would use weekly.

> *"I'd like to be able to go in and say Anna had posted 80% of my invoices, Becky had posted 20%, so I can track workload. And also if there are errors I can just pull off a report and see who's processed what."* — Emily
> 

---

### 5. Audit Trail is Too Vague to be Useful

**Who:** Emily

Xero's audit trail frequently logs changes as "bill was amended" without specifying what was changed or what the previous value was. Emily raised this in the context of investigating incorrect entries: knowing *that* something changed tells you nothing about *whether* the change was intentional, *what* it was before, or *who* should be followed up with.

This limits AirHop's ability to conduct internal control reviews and increases the manual investigation burden when reconciliation issues arise.

---

### 6. No Native Invoice On-Hold Status

**Who:** Emily

When an invoice is disputed or rejected, Xero has no built-in "on hold" or "disputed" status. The current workaround is to manually edit the bill reference field — adding text like "REJECTED" or "ON HOLD" — which risks polluting the reference field permanently if the period closes before the reference is cleaned up. Emily described this as an operational headache that creates noise in the data.

A proper invoice status workflow (draft → queried → on hold → approved → paid) would remove this entirely.

---

### 7. Remittances Are Sent Manually, One by One

**Who:** Emily

After a payment run is completed in Xero, Emily's team must manually navigate to each supplier, click send remittance, and confirm the email — for every payment in the run. This was flagged as an obviously automatable step: once a payment is posted, the remittance should fire automatically.

> *"Once the payment run's processed in Xero, we have to go in and then physically click send remittance, send email — if Xero could send those remittances out itself that takes another step away from us."* — Emily
> 

---

### 8. Stock Management is Untracked and Fragmented

**Who:** Callum, Claire, Niro, Tim

Stock was described by Tim as "really poor as a group across Europe." AirHop knows what sites sell but not precisely what they buy or consume. The current setup:

- **Sortly** used for stock counting — no integration with Xero or Shopify
- Workflow: park managers do manual stock counts → download from Sortly → calculate in Excel → import journal into Xero
- Some stock is distributed by van from the Bristol hub with no digital tracking at all (outstanding April stock confirmations still unresolved at time of interview)
- Shopify fulfilment confirmations can arrive weeks late with incorrect amounts
- Callum described it as a "no man's land" — nobody clearly owns it outside of finance's immediate remit

Tim acknowledged this was a known gap but deprioritised because stock is a small share of total revenue. Full Xero stock integration was assessed as too complex given the need to connect both sales and purchase systems.

---

### 9. Excel Remains the Human Verification Layer — and This is a Risk

**Who:** Anita, Claire, Niro, Tim

Despite Xero being the official system of record, Excel is doing significant work that Xero cannot:

- **Scott's Add-In** (an Excel-to-Xero bridge set up by a former head of finance, Samantha Simon) connects spreadsheets directly to Xero's trial balance for at-a-glance variance checking. The current team does not fully understand how it works. Tim flagged this explicitly as a dependency risk.
- **Cash flow** is managed by Nick Thompson (Head of Finance) in a spreadsheet, not Xero
- **Budgets** live in spreadsheets, not Xero
- **Payroll schedule** is built in Excel, cross-referenced against PlanDay hours, then compared to payroll output
- **Reporting** requires exporting P&L and trial balances from Xero into Excel for consolidation

This reliance is not accidental — the team treats Excel as the "human check layer." Anita described it as how you verify things at the flick of a button. But it creates a fragility: if the Excel breaks or its hidden logic is lost, there is no system safety net.

---

### 10. Month-End is Pressurised and Dependency-Heavy

**Who:** Anna, Niro, Anita

Month-end was described as a high-pressure crunch by multiple interviewees. Anna noted the team has approximately **three days** to close the books once ledgers are finalised — there is little they can prepare in advance because processing cannot begin until that point. Anita described month-end as characterised by tight deadlines with no slack, and dependency on external systems and people (payroll provider outages during peak usage were a specific example).

A new payroll system that was supposed to save time has instead added approximately a day of extra work due to lack of transparency into backend processes. Critically, **parallel testing was not done** when switching payroll systems — a risk that materialised.

---

### 11. Xero's UX is Not Built for Accountants

**Who:** Anita, Claire, Anna

Anita and Anna both noted that Xero's layout does not match the mental model of a trained accountant. Specific issues:

- No debit/credit ledger view — requires extra clicks to see transaction-level detail compared to Sage
- Supplier and customer accounts are mixed together; "bills" vs "invoices" terminology is confusing
- Cannot view a batch of different invoices on a single page

**Sage** was consistently cited as the benchmark for how invoice and ledger workflows should feel. Both Anna and Tamika's previous jobs used tools (Sage, Business Central) that allowed bulk invoice upload via Excel templates — a capability Xero lacks, which creates bottlenecks during high-volume processing periods.

> *"Sage is more clear. The filters are better and when you're searching invoices you have more options to see... if you want to see a batch of different invoices at once, while in Xero you can't do that on one page."* — Anna
> 

---

### 12. Roller → Xero Revenue Integration is Manual Daily Work

**Who:** Callum

Group bookings are invoiced through Roller (AirHop's booking platform), not Xero — Xero only sees the transaction when payment hits the bank. Callum's daily routine involves:

1. Export card transaction data from Roller, split by payment method
2. Verify payouts received in Xero 2 days later
3. Reconcile MeYou (food/drink portal) payouts across all sites
4. Resolve cash variances from sites (can take up to a week)
5. Month-end: full Roller export compared against Xero revenue to catch misallocations

Roller has no PO number field, which forces manual Xero invoicing for specific clients who require it — creating more precision requirements than the standard Roller flow. Roller does have more Xero integration options available but the team has not had capacity to explore them.

---

### 13. Process Bypasses are Structural, Not Accidental

**Who:** Claire, Tim, Anna

Multiple interviewees described a pattern: staff bypass formal approval workflows for legitimate commercial reasons (e.g. a supplier needs to be paid same-day for an urgent delivery). Claire noted that large unexpected bills frequently arrive because someone ordered goods without raising a purchase order — meaning finance had no visibility that the liability existed.

Tim framed this philosophically: *"We break the rules — not accounting rules, just workflow rules. That's inherent to an agile, fast-moving business."* Any automation or agentic system built into this environment needs to accommodate legitimate exceptions, not just enforce the ideal workflow.

---

### 14. Xero Reporting is Too Basic for AirHop's Scale

**Who:** Tim, Claire, Anita

Xero's built-in reports are considered adequate for simple queries but insufficient for AirHop's operational needs:

- Cannot compare two sites within the same legal entity side-by-side
- No consolidated view across entities
- No budget integration

For group-level reporting, **Bright Analytics** pulls data from all territories (UK/Ireland on Xero, Germany on DatEv, Holland on Access) and maps local account codes to group P&L and balance sheet codes. Operational reporting is done in Power BI, which Charles maintains. Scott's Add-In provides Anita with a direct Xero-to-Excel link for trial balance variance checks.

---

## 💡 Automation Ideas & Product Signals

| Idea | Source | Priority Signal |
| --- | --- | --- |
| **Remittance auto-send** after payment run posted | Emily | Quick win — zero judgment required |
| **Invoice chase automation** at 7 and 14 days overdue | Emily | Draft + send; human approves template |
| **OCR invoice auto-population** (ApprovalMax Captcha already exists) | Tamika, Emily | Human review step still needed — OCR errors on utility bills |
| **Smarter bank reconciliation** with historic pattern matching | Callum | Needs confidence score + explainability |
| **PLEO transaction isolation** in bank rec | Emily | Prevents cross-account false matches |
| **Cross-entity contact/config sync** | Emily, Claire | Charles's portal is the current workaround |
| **Workload distribution report** for AP managers | Emily | Know who posted what, track team load |
| **Invoice on-hold / disputed status** | Emily | Removes reference field pollution |
| **Accruals/prepayments automation** (e.g. spread rent over periods) | Tim | High-value, high-frequency accounting task |
| **Fixed asset register management** | Tim | Described as "so painful to do, no one really does" |
| **Bulk invoice upload via Excel/CSV** | Tamika, Anna | Xero lacks what Business Central and Sage provided |
| **Fine-tuned model on top supplier invoice formats** | Tim | ~90% of invoices from ~10 suppliers — high ROI |
| **AI analytics on Xero data via spreadsheet** | Niro | Already doing this personally; wants it more integrated |
| **Sortly → Xero journal automation** | Niro | Download → Excel → import journal chain is fully automatable |

---

## 🤖 AI & Automation Appetite — Cross-Interview Summary

Every single interviewee independently arrived at the same preference: **human-in-the-loop, not fully autonomous**. The framing from Tim (Finance Director) was the clearest articulation of the group consensus:

> *"The invoice comes in. The system reads it and says: here's the invoice, this is what I think we should do. Is that right? The human approves it. That's what we want."* — Tim Mclure
> 

Key nuances:

- **Tamika:** Does not want approval at every step, but wants to review before finalisation — aware of what the system is doing
- **Anna:** Final approval button must always be a human; AI cannot handle exceptions to normal rules (e.g. paying more than usual due to necessity)
- **Claire:** Automated coding won't know an invoice needs to be recharged across 30 sites — contextual judgment is irreplaceable
- **Callum:** Open to automation but low confidence in current Xero AI after bad mismatch experiences; wants it explained and testable
- **Tim:** Concerned about approval fatigue (approve → approve → approve); fine-tuning on company-specific supplier formats is the right architecture
- **Emily:** Open if it saves time; duplicate detection and remittance sending are the clearest safe automation targets
- **Niro:** Already using AI personally for analytics and email drafting; prefers AI to handle background work while humans make the final call
- **Anita:** Human oversight is non-negotiable; biggest risk is staff blindly accepting AI suggestions without understanding what they approved; accountability cannot be offloaded (*"It's the computer what did it isn't a defence"*)

---

## 🗺️ System Landscape

| System | Purpose | Integration status |
| --- | --- | --- |
| **Xero** | Core accounting, AP, invoicing, bank feeds | Central system |
| **ApprovalMax** | PO approvals, invoice matching | Connected to Xero |
| **PLEO** | Expense cards for park managers | Bank feed into Xero |
| **Roller** | Booking platform, group invoicing, revenue | Manual export → Xero |
| **MeYou (MeNu)** | Daily food/drink payment portal | Manual daily reconciliation |
| **Shopify** | Stock ordering | No integration with Xero |
| **Sortly** | Stock counting | No integration — manual CSV → Excel → Xero |
| **PlanDay** | Payroll hours tracking | Manual export → import file |
| **Bright Analytics** | Group-level P&L consolidation (UK/IE + DE + NL) | Pulls from Xero + DatEv + Access |
| **Power BI** | Operational reporting dashboards | Charles-managed |
| **Scott's Add-In** | Excel-to-Xero trial balance bridge | Works; original builder (Samantha Simon) no longer at company |
| **Day Out With The Kids** | Third-party ticket seller | API access to Roller; monthly commission reconciliation |

---

## 📌 Cross-Cutting Observations

**Invoice chasing is Callum's domain on the revenue side.** Both Tamika and Anna deferred to him when asked about overdue invoice processes. For suppliers, the AP team does chase for VAT invoices after pro-forma payments — manual ledger checks then manual emails.

**ApprovalMax is central but fragile.** The PO workflow runs through ApprovalMax, and every change in Xero's behaviour (like the auto-billing update) has a knock-on effect. Understanding the full Xero → ApprovalMax → Xero round-trip is essential before building anything that touches POs or bills.

**Sage is the benchmark.** Mentioned positively by Anna, Claire, Niro, and Tim. Any improvement to Xero's invoice or ledger UX should close the gap with Sage's batch views and filter capabilities.

**Charles is a key dependency.** His portal (cross-entity catalogue sync), the Power BI dashboard, and various integrations all sit with him. The team would not be able to replicate these independently. Emily, Claire and Tim all referenced him as the person who "fixes" cross-entity problems.

**Nick Thompson (Head of Finance) is the approval gatekeeper.** He was on leave during the interviews and returns approximately 20 June. Any further research access or formal engagement requires his sign-off.

**The Norway parent company is a wildcard.** A potential consolidation of UK/Ireland entities or a group-mandated platform switch (Coda and Microsoft Dynamics were mentioned as candidates) could change the entire technology landscape. Near-term solutions should either be platform-agnostic or export-friendly.

**The team is stretched and cash-starved on bandwidth.** Callum specifically noted that Roller has more Xero integration options available that he wants to explore, but month-end and ad-hoc obligations (bank switch, VAT rate change, audit requests) have crowded out any improvement work for six months. Any tool built for this team needs to be low-friction to set up and maintain.

---

## 📝 Side Note — Charles Win (BI Lead): Xero Solutions & Limitations

> Charles was on the interview schedule (TBC) but a formal research interview was not completed. The information below is drawn from the technical onboarding session on the same day and from references made by Tim, Claire, and Emily.
> 

### What Charles Built

The most relevant thing Charles has built for Xero is an **internal multi-portal management tool** — a JavaScript app hosted on AWS AppRunner that pushes bulk product catalogue updates across all Xero entities at once, removing the need to open each entity individually. This is the portal Emily and Claire both referenced when explaining how catalogue updates get synced across the business.

Technical details from the onboarding session:

- Uses **OAuth scoped to organisation access** across all entities
- A **shared cache** reduces redundant API calls when working across portals simultaneously
- **Activity and run history** is logged in DynamoDB for auditability
- Flagged as a potential reference model for the hackathon

### Known Limitations

- **Narrow scope:** the portal only handles catalogue and product updates. It does not solve the broader cross-entity problem — contacts, expense codes, reporting config, and general settings still require manual repetition in every entity.
- **Single point of knowledge:** the rest of the finance team does not understand how it works or how to maintain it. Tim flagged this explicitly: *"Unless we had Charles's knowledge and expertise, we would literally be doing that once for every entity."*
- **Lives outside Xero:** staff must go to a separate portal to make changes and trust they propagate — there is no visibility within Xero itself that the sync has happened.
- **Not generalisable:** purpose-built for one use case and cannot be adapted for other bulk cross-entity needs without Charles rebuilding it from scratch.

### The Broader BI Stack (Context)

Charles also manages the **Power BI reporting layer** — a nightly pipeline that pulls data from Roller, PlanDay, MeYou, and Mobaro via API dumps into Azure Blob, through Azure SQL transformations, and into a Power BI Semantic Model maintained by the Norwegian data partner Seabright. The semantic model is queried by an internal AI agent (*John Diamond*) running on Claude Sonnet to answer business questions against live finance data.

Xero sits at the source of this stack but is not directly queryable from Power BI — data flows out of Xero into the pipeline, not the other way around. The biggest practical pain Charles identified was **lack of documentation and inconsistent naming** in the semantic model — some bridge tables exist for historical reasons that even Seabright can no longer explain.

### Why This Matters

Charles's portal proves that cross-entity actions via the Xero API are technically feasible — OAuth works at scale, the API is usable across 20+ organisations, and a shared cache makes it performant. The gap is that the solution is narrow, undocumented, and not owned by the team. Any tool that tackles multi-entity management has a working internal proof-of-concept to learn from — and a clear gap to fill.