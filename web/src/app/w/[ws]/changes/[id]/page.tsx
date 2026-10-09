"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ChangeItem, type ChangeSet } from "@/lib/api";
import { useRole, useSession } from "@/lib/session";
import { useData } from "@/lib/use-data";
import {
  Avatar, Badge, Button, Card, ChangeBadge, EmptyState, ErrorNote, Icon, Input, Loading, Notice, OPERATION_LABELS, PageTitle,
} from "@/components/ui";

const AUTHORS = ["owner", "admin", "preparer"];
const DECIDERS = ["owner", "admin", "approver"];
const LIVE = new Set(["approved", "executing"]);

const STEPS = ["Draft", "Submitted", "Approved", "Applied"] as const;
function stepOf(status: ChangeSet["status"]): number {
  switch (status) {
    case "draft": return 0;
    case "submitted": return 1;
    case "approved": case "executing": return 2;
    case "completed": case "partial": case "failed": return 3;
    default: return 0;
  }
}

export default function ChangePage() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const router = useRouter();
  const { me } = useSession();
  const { role } = useRole(ws);
  const change = useData(() => api.change(ws, id), (c: ChangeSet) => LIVE.has(c.status));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!change.data || !me) return <Loading />;
  const c = change.data;
  const isAuthor = c.author.id === me.user.id;
  const isDecider = DECIDERS.includes(role ?? "");
  const canEdit = c.status === "draft" && (isAuthor || role === "owner" || role === "admin");
  const canDecide = c.status === "submitted" && isDecider && !isAuthor;
  // The API tells the author whether this change qualifies; it enforces the same rules.
  const canSelfApprove = c.status === "submitted" && isAuthor && isDecider && !c.self_approval_blocker;
  const canReview = c.needs_review && isDecider && !isAuthor;
  const canCancel = ["draft", "submitted"].includes(c.status) && (isAuthor || role === "owner" || role === "admin");
  const canRetry = ["partial", "failed"].includes(c.status) && DECIDERS.includes(role ?? "");

  async function act(fn: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await change.reload();
      after?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const items = c.items ?? [];
  const blocked = items.filter((i) => i.preflight_status === "blocked").length;
  const step = stepOf(c.status);
  const terminalBad = c.status === "rejected" || c.status === "cancelled";
  const authorName = c.author.name || c.author.email;
  const hasActions = (canEdit && AUTHORS.includes(role ?? "")) || canDecide || canSelfApprove || canRetry || canCancel || canReview
    || (c.status === "submitted" && isAuthor && !canSelfApprove);

  return (
    <>
      <PageTitle
        title={c.title}
        back={{ href: `/w/${ws}/changes`, label: "All changes" }}
        badge={<ChangeBadge status={c.status} />}
        subtitle={<span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
          <Avatar name={authorName} size={18} /> Proposed by {authorName}
          {c.self_approved && <Badge tone="amber" dot>Self-approved</Badge>}
        </span>}
      />
      {c.reason && <p className="-mt-3 mb-5 max-w-2xl text-sm leading-relaxed text-muted">{c.reason}</p>}
      <ErrorNote message={error ?? change.error} />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* Items */}
        <div className="min-w-0 space-y-3">
          <h2 className="eyebrow">{items.length} {items.length === 1 ? "item" : "items"} in this change</h2>
          {items.length === 0 && <Card><EmptyState icon="changes" title="No items">This change has nothing in it.</EmptyState></Card>}
          {items.map((item) => (
            <Item key={item.id} item={item} editable={canEdit}
              onRemove={() => act(() => api.removeChangeItem(ws, c.id, item.id))}
              onEdit={(payload) => act(() => api.editChangeItem(ws, c.id, item.id, payload))} />
          ))}
        </div>

        {/* Status + decisions */}
        <aside className="space-y-4 xl:sticky xl:top-20">
          <Card padded>
            <h2 className="eyebrow mb-4">Progress</h2>
            <ol className="relative space-y-4">
              {STEPS.map((s, i) => {
                const done = !terminalBad && i < step;
                const current = !terminalBad && i === step;
                return (
                  <li key={s} className="relative flex items-center gap-3">
                    {i < STEPS.length - 1 && <span className={`absolute left-[11px] top-6 h-4 w-px ${done ? "bg-brand" : "bg-border"}`} />}
                    <span className={`z-10 grid h-6 w-6 place-items-center rounded-full text-[11px] font-semibold ${
                      done ? "bg-brand text-white" : current ? "bg-ink text-white ring-4 ring-ink/10" : "bg-surface-sunken text-subtle ring-1 ring-inset ring-border"}`}>
                      {done ? <Icon name="check" size={13} /> : i + 1}
                    </span>
                    <span className={`text-sm ${current ? "font-semibold" : done ? "text-foreground" : "text-muted"}`}>
                      {i === 3 && c.status === "partial" ? "Partly applied" : i === 3 && c.status === "failed" ? "Failed" : s}
                    </span>
                  </li>
                );
              })}
            </ol>
            {terminalBad && (
              <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                This change was {c.status === "rejected" ? "rejected" : "cancelled"}.
              </p>
            )}
            {(c.decided_by || c.reviewed_by) && (
              <dl className="mt-5 space-y-3 border-t border-border pt-4 text-[13px]">
                {c.decided_by && (
                  <div>
                    <dt className="text-muted">{c.status === "rejected" ? "Rejected" : c.self_approved ? "Self-approved" : "Approved"} by</dt>
                    <dd className="mt-0.5 font-medium">{c.decided_by.name || c.decided_by.email}</dd>
                    {c.decision_note && <dd className="mt-1 rounded-lg bg-surface-sunken px-3 py-2 text-muted">“{c.decision_note}”</dd>}
                  </div>
                )}
                {c.reviewed_by && (
                  <div>
                    <dt className="text-muted">Reviewed by</dt>
                    <dd className="mt-0.5 font-medium">{c.reviewed_by.name || c.reviewed_by.email}</dd>
                    {c.review_note && <dd className="mt-1 rounded-lg bg-surface-sunken px-3 py-2 text-muted">“{c.review_note}”</dd>}
                  </div>
                )}
              </dl>
            )}
          </Card>

          {c.self_approved && !c.reviewed_by && (
            <Notice tone="warn">
              <p className="mb-1 font-medium">Needs a second pair of eyes</p>
              <p className="text-[13px]">Self-approved: nobody else has looked at this change yet. Someone who can approve changes should review it.</p>
              {canReview && (
                <div className="mt-3 space-y-2">
                  <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Review note (optional)" aria-label="Review note" />
                  <Button size="sm" disabled={busy} onClick={() => act(() => api.reviewChange(ws, c.id, note), () => setNote(""))}>Mark reviewed</Button>
                </div>
              )}
            </Notice>
          )}

          {hasActions && (
            <Card padded className="space-y-3">
              <h2 className="eyebrow">{canDecide || canSelfApprove ? "Your decision" : "Actions"}</h2>

              {canEdit && AUTHORS.includes(role ?? "") && (
                <Button className="w-full" disabled={busy || blocked > 0} onClick={() => act(() => api.submitChange(ws, c.id))}>
                  {blocked ? `Fix ${blocked} blocked item${blocked === 1 ? "" : "s"} to submit` : "Submit for approval"}
                </Button>
              )}

              {canDecide && (
                <div className="space-y-2.5">
                  <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required to reject)" aria-label="Decision note" />
                  <div className="flex gap-2">
                    <Button className="flex-1" disabled={busy} icon="check" onClick={() => act(() => api.approveChange(ws, c.id, note || undefined))}>
                      Approve and apply
                    </Button>
                    <Button variant="danger" disabled={busy || !note.trim()} onClick={() => act(() => api.rejectChange(ws, c.id, note))}>Reject</Button>
                  </div>
                </div>
              )}

              {canSelfApprove && (
                <div className="space-y-2.5">
                  <p className="rounded-lg bg-amber-50 px-3 py-2.5 text-[13px] leading-relaxed text-amber-900">
                    You proposed this and you&apos;re the only approver, so you can approve it yourself: it only brings organisations into
                    line with the group standard. Say why. It waits in the review queue until someone else looks at it.
                  </p>
                  <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why approve it yourself? (required)" aria-label="Self-approval note" />
                  <Button className="w-full" disabled={busy || !note.trim()} onClick={() => act(() => api.approveChange(ws, c.id, note))}>
                    Approve my own change
                  </Button>
                </div>
              )}

              {c.status === "submitted" && isAuthor && !canSelfApprove && (
                <p className="flex gap-2 rounded-lg bg-surface-sunken px-3 py-2.5 text-[13px] leading-relaxed text-muted">
                  <Icon name="clock" size={16} className="mt-0.5 shrink-0" />
                  <span>Waiting for another approver. You can&apos;t approve your own change{c.self_approval_blocker ? <>: {c.self_approval_blocker}</> : "."}</span>
                </p>
              )}

              {canRetry && <Button className="w-full" icon="refresh" disabled={busy} onClick={() => act(() => api.retryChange(ws, c.id))}>Retry failed items</Button>}
              {canCancel && (
                <Button variant="ghost" className="w-full text-muted" disabled={busy}
                  onClick={() => act(() => api.cancelChange(ws, c.id), () => router.push(`/w/${ws}/changes`))}>
                  Cancel change
                </Button>
              )}
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}

function describe(item: ChangeItem): string {
  const p = item.payload as Record<string, string | undefined>;
  const category = item.tracking_category?.name ?? "(category)";
  const option = `${category} / ${item.tracking_option?.name ?? "(option)"}`;
  switch (item.operation) {
    case "create_tracking_category": {
      const options = (item.payload as { options?: string[] }).options ?? [];
      return `${p.name} · ${options.length ? `options: ${options.join(", ")}` : "no options"}`;
    }
    case "create_tracking_option": return `${category} → new option ${p.name}`;
    case "update_tracking_category": return `${category}: name → ${p.name}`;
    case "update_tracking_option": return `${option}: name → ${p.name}`;
    case "archive_tracking_category": return category;
    case "archive_tracking_option": return option;
  }
  if (item.operation === "create_account") {
    return `${p.code} ${p.name} · ${p.type}${p.tax_type ? ` · tax ${p.tax_type}` : " · Xero's default tax"}`;
  }
  const acct = item.account ? `${item.account.code ?? "—"} ${item.account.name}` : "(account)";
  if (item.operation === "archive_account") return acct;
  const changes = Object.entries(p).map(([k, v]) => `${k} → ${v}`).join(", ");
  return `${acct}: ${changes}`;
}

const OP_ICON = (op: string) => (op.startsWith("create") ? "plus" : op.startsWith("archive") ? "archive" : "edit") as "plus" | "archive" | "edit";
const OP_TONE = (op: string) =>
  op.startsWith("create") ? "bg-emerald-50 text-emerald-700" : op.startsWith("archive") ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700";

function Item({ item, editable, onRemove, onEdit }: {
  item: ChangeItem; editable: boolean; onRemove: () => void; onEdit: (payload: Record<string, unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const p = item.payload as Record<string, string | undefined>;
  const [code, setCode] = useState(p.code ?? "");
  const [taxType, setTaxType] = useState(p.tax_type ?? "");
  const blocked = item.preflight_status === "blocked" && item.status === "pending";

  return (
    <Card className={`p-4 ${blocked ? "border-red-200" : ""}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${OP_TONE(item.operation)}`}><Icon name={OP_ICON(item.operation)} size={17} /></span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{item.entity_name}</p>
          <p className="text-xs text-muted">{OPERATION_LABELS[item.operation]}{item.attempt > 1 && <> · attempt {item.attempt}</>}</p>
        </div>
        <ChangeBadge status={item.status} />
        {editable && (
          <span className="flex gap-1">
            {item.operation === "create_account" && (
              <Button variant="ghost" size="sm" icon="edit" onClick={() => setEditing((e) => !e)}>{editing ? "Close" : "Edit"}</Button>
            )}
            <Button variant="ghost" size="sm" icon="trash" onClick={onRemove}>Remove</Button>
          </span>
        )}
      </div>
      <p className="mt-3 overflow-x-auto rounded-lg bg-surface-sunken px-3 py-2 font-mono text-xs leading-relaxed text-foreground/80">{describe(item)}</p>
      {editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Input value={code} onChange={(e) => setCode(e.target.value)} aria-label="Account code" placeholder="Code" className="w-28" />
          <Input value={taxType} onChange={(e) => setTaxType(e.target.value)} aria-label="Tax type" placeholder="Tax type (blank = Xero default)" className="w-72" />
          <Button onClick={() => { onEdit({ code, tax_type: taxType || null }); setEditing(false); }}>Save</Button>
        </div>
      )}
      {blocked && (
        <ul className="mt-3 space-y-1 rounded-lg bg-red-50 px-3 py-2.5 text-xs text-red-700">
          {item.preflight_messages.map((m, i) => <li key={i} className="flex gap-2"><Icon name="alert" size={14} className="mt-px shrink-0" />{m}</li>)}
        </ul>
      )}
      {item.error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2.5 text-xs text-red-700">{item.error}</p>}
      {(item.before || item.after) && (
        <details className="group mt-3 text-xs">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-muted transition hover:text-foreground">
            <Icon name="chevronRight" size={14} className="transition group-open:rotate-90" /> Before / after in Xero
          </summary>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <Snapshot title="Before" data={pick(item.before)} />
            <Snapshot title="After" data={pick(item.after)} />
          </div>
        </details>
      )}
    </Card>
  );
}

function Snapshot({ title, data }: { title: string; data: Record<string, unknown> | null }) {
  return (
    <div className="rounded-lg border border-border">
      <p className="eyebrow border-b border-border bg-surface-sunken/60 px-3 py-1.5">{title}</p>
      <pre className="overflow-x-auto px-3 py-2 font-mono text-[11px] leading-relaxed">{data ? JSON.stringify(data, null, 2) : "—"}</pre>
    </div>
  );
}

// Show the fields a person cares about, not Xero's whole object.
function pick(a: Record<string, unknown> | null) {
  if (!a) return null;
  const keys = ["Code", "Name", "Type", "TaxType", "Status", "Description"];
  const out: Record<string, unknown> = Object.fromEntries(keys.filter((k) => a[k] !== undefined).map((k) => [k, a[k]]));
  // A tracking category: list its options by name.
  if (Array.isArray(a.Options)) out.Options = (a.Options as { Name?: string }[]).map((o) => o.Name);
  return out;
}
